import itertools
import uuid

from sqlalchemy import ForeignKey, Column, Integer, String, Float
from sqlalchemy.orm import relationship

from htsohm.db import Base, GasLoading, SurfaceArea, VoidFraction, AtomSite, LennardJones
from htsohm.db.structure import Structure

class Material(Base):
    """Declarative class mapping to table storing material/simulation data.

    Attributes:
        id (int): database table primary_key.
        run_id (str): identification string for run.
    """
    __tablename__ = 'materials'

    id           = Column(Integer, primary_key=True)
    run_id       = Column(String(50))
    uuid         = Column(String(40))
    parent_id    = Column(Integer, ForeignKey('materials.id'))
    perturbation = Column(String(10))
    generation   = Column(Integer)

    # structure properties
    unit_cell_volume     = Column(Float)
    number_density       = Column(Float)
    average_epsilon      = Column(Float)
    average_sigma        = Column(Float)

    # relationships
    gas_loading       = relationship("GasLoading", cascade="all, delete-orphan")
    surface_area      = relationship("SurfaceArea", cascade="all, delete-orphan")
    void_fraction     = relationship("VoidFraction", cascade="all, delete-orphan")
    structure         = relationship("Structure", uselist=False, back_populates="material", cascade="all, delete-orphan")
    parent            = relationship("Material", remote_side=[id])

    def __init__(self, run_id=None, parent=None, structure=None):
        """Init material-row.

        Args:
            self (class): row in material table.
            run_id : identification string for run (default = None).

        Initializes row in materials datatable.

        """
        self.uuid = str(uuid.uuid4())
        if parent:
            self.parent = parent
            self.parent_id = parent.id
        self.run_id = run_id
        if structure is None:
            self.structure = Structure()
        else:
            self.structure = structure

    @staticmethod
    def one_atom_new(sigma, epsilon, a, b, c):
        structure = Structure(a, b, c,
                [AtomSite(atom_type="A_0", x=1.0, y=1.0, z=1.0, q=0.0)],
                [LennardJones(atom_type="A_0", sigma=sigma, epsilon=epsilon)])
        m = Material(structure=structure)
        return m

    def eight_atom_cubic(sigma, epsilon, a, b, c):
        atomsites = itertools.product((0.0, 0.5), (0.0, 0.5), (0.0, 0.5))
        structure = Structure(a, b, c,
                [AtomSite(atom_type="A_0", x=a[0], y=a[1], z=a[2], q=0.0) for a in atomsites],
                [LennardJones(atom_type="A_0", sigma=sigma, epsilon=epsilon)])
        m = Material(structure=structure)
        m.unit_cell_volume = m.structure.volume
        m.number_density = 8 / m.unit_cell_volume
        return m


    @staticmethod
    def cube_pore_new(sigma, epsilon, num_atoms, atom_diameter):
        # lattice constant a is calculated from number of atoms times the atom_diameter
        a = num_atoms * atom_diameter

        atom_sites = []
        for xi in range(num_atoms):
            for yi in range(num_atoms):
                for zi in range(num_atoms):
                    # only add indices that are in one of the three boundary planes, i.e index == 0
                    if min(xi, yi, zi) == 0:
                        x = xi * atom_diameter / a
                        y = yi * atom_diameter / a
                        z = zi * atom_diameter / a
                        atom_sites.append(AtomSite(atom_type="A_0", x=x, y=y, z=z, q=0.0))

        structure = Structure(a, a, a, atom_sites, [LennardJones(atom_type="A_0", sigma=sigma, epsilon=epsilon)])
        m = Material(structure=structure)
        return m



    def clone(self):
        copy = super(Material, self).clone()
        copy.parent = self
        copy.parent_id = self.id
        copy.structure = self.structure.clone()
        return copy

    def exclude_cols(self):
        return ['uuid', 'id']

    def __repr__(self):
        return "(%s: %s-%s p: %s)" % (self.run_id, str(self.id), self.uuid, self.parent_id)
