
from datetime import datetime
from glob import glob
import math
import os
import random
from random import uniform
import sys

import numpy as np

from htsohm import pseudomaterial_generator, load_config_file, db
from htsohm.db import Material
from htsohm.simulation.run_all import run_all_simulations
from htsohm.figures import delaunay_figure
import htsohm.select.triangulation as selector_tri
import htsohm.select.density_bin as selector_bin
import htsohm.select.best as selector_best
import htsohm.select.last_best as selector_last_best
import htsohm.select.specific as selector_specific

def print_block(string):
    print('{0}\n{1}\n{0}'.format('=' * 80, string))


def calc_bin(value, bound_min, bound_max, bins):
    """Find bin in parameter range.
    Args:
        value (float): some value, the result of a simulation.
        bound_min (float): lower limit, defining the parameter-space.
        bound_max (float): upper limit, defining the parameter-space.
        bins (int): number of bins used to subdivide parameter-space.
    Returns:
        Bin(int) corresponding to the input-value.
    """
    step = (bound_max - bound_min) / bins
    assigned_bin = (value - bound_min) // step
    assigned_bin = min(assigned_bin, bins-1)
    assigned_bin = max(assigned_bin, 0)
    return int(assigned_bin)

def calc_bins(box_r, num_bins, prop1range=(0.0, 1.0), prop2range=(0.0, 1.0)):
    return [(calc_bin(b[0], *prop1range, num_bins), calc_bin(b[1], *prop2range, num_bins)) for b in box_r]

def empty_lists_2d(x,y):
    return [[[] for j in range(x)] for i in range(y)]

def dump_restart(path, box_d, box_r, bin_counts, bin_materials, bins, gen):
    np.savez(path, box_d, box_r, bin_counts, bin_materials, bins, gen)

def load_restart(path):
    npzfile = np.load(path, allow_pickle=True)
    return [npzfile[v] if npzfile[v].size != 1 else npzfile[v].item() for v in npzfile.files]

def serial_runloop(config_path):
    """
    Args:
        run_id (str): identification string for run.

    """

    run_id = datetime.now().isoformat()
    config = load_config_file(config_path)
    print(config)

    children_per_generation = config['children_per_generation']
    # prop1 = config['prop1']
    # prop2 = config['prop2']
    prop1range = config['prop1range']
    prop2range = config['prop2range']
    verbose = config['verbose'] if 'verbose' in config else False
    vf_subtype = config['void_fraction_subtype'] if 'void_fraction_subtype' in config else 'raspa'
    num_bins = config['number_of_convergence_bins']
    benchmarks = config['benchmarks']
    next_benchmark = benchmarks.pop(0)
    last_benchmark_reached = False
    load_restart_path = config['load_restart_path'] if 'load_restart_path' in config else False
    initial_points = config['initial_points'] if 'initial_points' in config else "random"

    dbcs = config["database_connection_string"]
    db.init_database(dbcs, backup=(load_restart_path != False))
    session = db.get_session()
    engine = db.get_engine()

    print('{:%Y-%m-%d %H:%M:%S}'.format(datetime.now()))

    if load_restart_path:
        if load_restart_path == "auto":
            restart_files = glob("*.txt.npz")
            restart_files.sort(key=os.path.getmtime)
            if len(restart_files) == 0:
                print("ERROR: no txt.npz restart file in the current directory; auto cannot be used.")
                return
            load_restart_path = restart_files[-1]
            if len(restart_files) > 1:
                print("WARNING: more than one txt.npz file found in this directory. Using last one: %s" % load_restart_path)

        print("Restarting from file: %s" % load_restart_path)
        box_d, box_r, bin_counts, bin_materials, bins, start_gen = load_restart(load_restart_path)
        print("Restarting at generation %d" % start_gen)
        print("There are currently %d materials" % len(box_r))

        extra_materials = session.query(Material).filter(Material.id > len(box_r)).all()
        if len(extra_materials) > 0:
            if len(extra_materials) > children_per_generation and not config['override_restart_errors']:
                print("There are %d extra materials in the database, which is more than the %d " \
                      "children per generation. Is this the right restart file?" %
                      (len(extra_materials), children_per_generation))
                sys.exit(1)
            print("The database has an extra %d materials in it; deleting..." % len(extra_materials))

            print("delete from materials where id > %d" % len(box_r))
            engine.execute("delete from materials where id > %d" % len(box_r))
            engine.execute("delete from gas_loadings where material_id > %d" % len(box_r))
            engine.execute("delete from surface_areas where material_id > %d" % len(box_r))
            engine.execute("delete from void_fractions where material_id > %d" % len(box_r))
            engine.execute("delete from structures where material_id > %d" % len(box_r))
            engine.execute("delete from lennard_jones where structure_id > %d" % len(box_r))
            engine.execute("delete from atom_sites where structure_id > %d" % len(box_r))

    else:
        if session.query(Material).count() > 0:
            print("ERROR: cannot have existing materials in the database for a new run")
            sys.exit(1)


        # define variables that are needed for state
        bin_counts = np.zeros((num_bins, num_bins))
        bin_materials = empty_lists_2d(num_bins, num_bins)
        box_d = np.zeros(children_per_generation, dtype=int)
        box_r = -1 * np.ones((children_per_generation, 2))
        bins = set()

        # generate initial generation of random materials
        if config['initial_points_random_seed']:
            print("applying random seed to initial points: %d" % config['initial_points_random_seed'])
            random.seed(config['initial_points_random_seed'])

        materials = []
        if initial_points == "cubic":
            scfg = config["structure_parameters"]
            for i in range(children_per_generation):
                materials.append(Material.eight_atom_cubic(
                    sigma = uniform(*scfg["sigma_limits"]),
                    epsilon = uniform(*scfg["epsilon_limits"]),
                    a = uniform(*scfg["lattice_constant_limits"]),
                    b = uniform(*scfg["lattice_constant_limits"]),
                    c = uniform(*scfg["lattice_constant_limits"])))
        else: # random
            for i in range(children_per_generation):
                print("Material Index: ", i)
                materials.append(pseudomaterial_generator.random.new_material(run_id, config["structure_parameters"]))

        for i, material in enumerate(materials):
            run_all_simulations(material, config)
            material.generation = 0
            session.add(material)
            session.commit()

            box_d[i] = material.id
            if vf_subtype == "raspa":
                vf = material.void_fraction[0].void_fraction
            elif vf_subtype == "geo":
                vf = material.void_fraction[0].void_fraction_geo
            else:
                raise(Exception("void fraction subtype not recognized"))

            box_r[i,:] = (vf, material.gas_loading[0].absolute_volumetric_loading)
            # box_r[i,:] = (material[prop1], material[prop2])

        random.seed() # flush the seed so that only the initial points are set, not generated points

        all_bins = calc_bins(box_r, num_bins, prop1range=prop1range, prop2range=prop2range)
        for i, (bx, by) in enumerate(all_bins):
            bin_counts[bx,by] += 1
            bin_materials[bx][by].append(i)
        bins = set(all_bins)

        output_path = os.path.join(config['output_dir'], "binplot_0.png")
        delaunay_figure(box_r, num_bins, output_path, bins=bin_counts, \
                            title="Starting random materials", show_triangulation=False, show_hull=False, \
                            prop1range=prop1range, prop2range=prop2range)

        start_gen = 1

    for gen in range(start_gen, config['max_generations'] + 1):
        parents_r = parents_d = []
        perturbation_methods = [""] * children_per_generation
        bin_scores = None
        if config['selector_type'] == 'simplices-or-hull':
            parents_d, parents_r = selector_tri.choose_parents(children_per_generation, box_d, box_r, config['simplices_or_hull'])
        elif config['selector_type'] == 'density-bin':
            parents_d, parents_r, _ = selector_bin.choose_parents(children_per_generation, box_d, box_r, bin_materials)
        elif config['selector_type'] == 'density-bin-neighbor-radius':
            parents_d, parents_r, bin_scores = selector_bin.choose_parents(children_per_generation, box_d, box_r, bin_materials, score_by_empty_neighbors=True)
        elif config['selector_type'] == 'best':
            parents_d, parents_r, _ = selector_best.choose_parents(children_per_generation, box_d, box_r)
        elif config['selector_type'] == 'last-best':
            parents_d, parents_r, _ = selector_last_best.choose_parents(children_per_generation, box_d, box_r)
        elif config['selector_type'] == 'specific':
            parents_d, parents_r, _ = selector_specific.choose_parents(children_per_generation, box_d, box_r, config['selector_specific_id'])

        # mutate materials and simulate properties
        new_box_d = np.zeros(children_per_generation)
        new_box_r = -1 * np.ones((children_per_generation, 2))
        for i in range(children_per_generation):
            print("Material Index: ", i + gen * children_per_generation)
            if config['generator_type'] == 'random':
                material = pseudomaterial_generator.random.new_material(run_id, config["structure_parameters"])
                perturbation_methods = None
            elif config['generator_type'] == 'mutate':
                material = pseudomaterial_generator.mutate.mutate_material(run_id, parents_d[i], config["structure_parameters"])
                perturbation_methods[i] = material.perturbation

            run_all_simulations(material, config)
            material.generation = gen
            session.add(material)
            session.commit()

            new_box_d[i] = material.id
            if vf_subtype == "raspa":
                vf = material.void_fraction[0].void_fraction
            elif vf_subtype == "geo":
                vf = material.void_fraction[0].void_fraction_geo
            else:
                raise(Exception("void fraction subtype not recognized"))
            new_box_r[i,:] = (vf, material.gas_loading[0].absolute_volumetric_loading)
            # new_box_r[i,:] = (material[prop1], material[prop2])

        # TODO: bins for methane loading?
        all_bins = calc_bins(new_box_r, num_bins, prop1range=prop1range, prop2range=prop2range)
        for i, (bx, by) in enumerate(all_bins):
            bin_counts[bx,by] += 1
            material_index = i + gen * children_per_generation
            bin_materials[bx][by].append(material_index)
        new_bins = set(all_bins) - bins
        bins = bins.union(new_bins)

        # evaluate algorithm effectiveness
        bin_fraction_explored = len(bins) / num_bins ** 2
        if verbose:
            print_block('%s GENERATION %s: %5.2f%%' % (run_id, gen, bin_fraction_explored * 100))
        while bin_fraction_explored >= next_benchmark:
            print_block("%s: %5.2f%% exploration accomplished at generation %d" %
                ('{:%Y-%m-%d %H:%M:%S}'.format(datetime.now()), bin_fraction_explored * 100, gen))
            if benchmarks:
                next_benchmark = benchmarks.pop(0)
            else:
                last_benchmark_reached = True

        if 'output_all_graphs' in config and config['output_all_graphs']:
            output_path = os.path.join(config['output_dir'], "binplot_%d.png" % gen)
            delaunay_figure(box_r, num_bins, output_path, children=new_box_r, parents=parents_r,
                            bins=bin_counts, new_bins=new_bins,
                            title="Generation %d: %d/%d (+%d) %5.2f%% (+%5.2f %%)" %
                                (gen, len(bins), num_bins ** 2, len(new_bins),
                                100*float(len(bins)) / num_bins ** 2, 100*float(len(new_bins)) / num_bins ** 2 ),
                            patches=None, prop1range=prop1range, prop2range=prop2range, \
                            perturbation_methods=perturbation_methods, show_triangulation=False, show_hull=False,
                            bin_scores=bin_scores)

        if 'output_tri_graph' in config and config['output_tri_graph'] and (gen <= 10 or (gen <=50 and gen % 10 == 0) or
            (gen <=500 and gen % 50 == 0) or gen % 100 == 0 or last_benchmark_reached):
            output_path = os.path.join(config['output_dir'], "triplot_%d.png" % gen)
            delaunay_figure(box_r, num_bins, output_path, children=new_box_r, parents=parents_r,
                            bins=bin_counts, new_bins=new_bins,
                            title="Generation %d: %d/%d (+%d) %5.2f%% (+%5.2f %%)" %
                                (gen, len(bins), num_bins ** 2, len(new_bins),
                                100*float(len(bins)) / num_bins ** 2, 100*float(len(new_bins)) / num_bins ** 2 ),
                            patches=None, prop1range=prop1range, prop2range=prop2range, \
                            perturbation_methods=perturbation_methods)

        box_d = np.append(box_d, new_box_d, axis=0)
        box_r = np.append(box_r, new_box_r, axis=0)

        restart_path = os.path.join(config['output_dir'], "restart_%d.txt.npz" % gen)
        dump_restart(restart_path, box_d, box_r, bin_counts, bin_materials, bins, gen + 1)

        if last_benchmark_reached:
            break
