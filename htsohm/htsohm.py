import sys
import os
from datetime import datetime
import yaml

import numpy as np

from htsohm import generate as gen
from htsohm import simulate as sim
from htsohm import binning as bng
from htsohm import mutate as mut
from htsohm.runDB_declarative import RunData, session

def write_config_file(children_per_generation, number_of_atomtypes, strength_0,
    number_of_bins, max_generations):
    run_id = datetime.now().isoformat()
    wd = os.environ['HTSOHM_DIR']      # specify working directory
    config_file = os.path.join(wd, 'config', run_id + '.yaml')
    run_config = {
        "run-id" : run_id,
        "children-per-generation" : children_per_generation,
        "number-of-atom-types" : number_of_atomtypes,
        "initial-mutation-strength" : strength_0,
        "number-of-bins" : number_of_bins,
        "max-number-of-generations" : max_generations}
    with open(config_file, "w") as file:
        yaml.dump(run_config, file, default_flow_style=False)
    return run_config

def read_config(run_config):
    run_id = run_config["run-id"]
    children_per_generation = run_config["children-per-generation"]
    number_of_atomtypes = run_config["number-of-atom-types"]

    return run_id, children_per_generation, number_of_atomtypes

def seed_generation(run_config):
    run_id, children_per_generation, number_of_atomtypes = read_config(run_config)
    generation = 0
    ids = gen_ids(generation, children_per_generation)
    primary_keys = []
    for i in ids:
        new_material = RunData(run_id, str(i), generation)
        session.add(new_material)
        session.commit()
        primary_keys.append(new_material.id)
    gen.generate(children_per_generation, number_of_atomtypes, run_id)
    for i in primary_keys:
        sim.run_all_simulations(i)
    session.commit()

def first_generation(run_config):
    run_id, children_per_generation, number_of_atomtypes = read_config(run_config)
    strength_0 = run_config["initial-mutation-strength"]
    generation = 1
    ids = gen_ids(generation, children_per_generation)
    primary_keys = []
    for i in ids:
        new_material = RunData(run_id, str(i), generation)
        session.add(new_material)
        session.commit()
        primary_keys.append(new_material.id)
    status = "Dummy test:   RUNNING"
    while status == "Dummy test:   RUNNING":
        # Select parents, add IDs to database...
        next_materials_list = bng.select_parents(run_id,
            children_per_generation, generation)
        session.commit()               # parent_ids staged by bng.select_parents()
        status = sim.dummy_test(run_id, next_materials_list, status, generation)
        session.commit()               # within loop so "fail" parents aren't re-selected
    mut.first_s(run_id, strength_0)    # Create strength-parameter array `run_id`.npy
    mut.mutate(run_id, generation)     # Create first generation of child-materials
    for i in primary_keys:
        sim.run_all_simulations(i)
    session.commit()

def next_generation(run_config, generation):
    run_id, children_per_generation, number_of_atomtypes = read_config(run_config)
    strength_0 = run_config["initial-mutation-strength"]
    ids = gen_ids(generation, children_per_generation)
    primary_keys = []
    for i in ids:
        new_material = RunData(run_id, str(i), generation)
        session.add(new_material)
        session.commit()
        primary_keys.append(new_material.id)
    status = "Dummy test:   RUNNING"
    while status == "Dummy test:   RUNNING":
        # Select parents, add IDs to database...
        next_materials_list = bng.select_parents(run_id,
            children_per_generation, generation)
        session.commit()               # parent_ids staged by bng.select_parent()
        status = sim.dummy_test(run_id, next_materials_list, status, generation)
        session.commit()               # within loop so "fail" parents aren't re-selected
    mut.calculate_s(run_id, generation)
    mut.mutate(run_id, generation)
    for i in primary_keys:
        sim.run_all_simulations(i)
    session.commit()

def htsohm(children_per_generation,    # number of materials per generation
           number_of_atomtypes,        # number of atom-types per material
           strength_0,                 # intial strength parameter
           number_of_bins,             # number of bins for analysis
           max_generations=20):        # maximum number of generations

    run_config = write_config_file(children_per_generation,
        number_of_atomtypes, strength_0, number_of_bins, max_generations)

    for generation in range(max_generations):
        if generation == 0:                     # SEED GENERATION
            seed_generation(run_config)
        elif generation == 1:                   # FIRST GENERATION
            first_generation(run_config)
        elif generation >= 2:                   # SECOND GENERATION(S), and on...
            next_generation(run_config, generation)

def gen_ids(generation, children_per_generation):
    first = generation * children_per_generation
    last = (generation + 1) * children_per_generation
    gen_ids = np.arange(first, last)

    return gen_ids
