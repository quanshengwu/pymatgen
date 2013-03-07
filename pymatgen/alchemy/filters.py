#!/usr/bin/env python

"""
This module defines filters for Transmuter object.
"""

from __future__ import division

__author__ = "Will Richards, Shyue Ping Ong, Stephen Dacek"
__copyright__ = "Copyright 2011, The Materials Project"
__version__ = "1.0"
__maintainer__ = "Will Richards"
__email__ = "wrichards@mit.edu"
__date__ = "Sep 25, 2012"

from pymatgen.core.periodic_table import smart_element_or_specie
from pymatgen.serializers.json_coders import MSONable
from pymatgen.analysis.structure_matcher import StructureMatcher,\
    ElementComparator
from pymatgen.symmetry.finder import SymmetryFinder
import abc


class AbstractStructureFilter(MSONable):
    """
    Abstract structure filter class.
    """
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def test(self, structure):
        """
        Returns a boolean for any structure. Structures that return true are
        kept in the Transmuter object during filtering.
        """
        return

    @staticmethod
    def from_dict(d):
        for trans_modules in ['filters']:
            mod = __import__('pymatgen.alchemy.' + trans_modules,
                             globals(), locals(), [d['@class']], -1)
            if hasattr(mod, d['@class']):
                trans = getattr(mod, d['@class'])
                return trans(**d['init_args'])
        raise ValueError("Invalid filter dict")


class ContainsSpecieFilter(AbstractStructureFilter):
    """
    Filter for structures containing certain elements or species.
    By default compares by atomic number
    """

    def __init__(self, species, strict_compare=False, AND=True, exclude=False):
        """
        Args:
            species:
                list of species to look for
            AND:
                whether all species must be present to pass (or fail)
                filter.
            strict_compare:
                if true, compares objects by specie or element object
                if false, compares atomic number
            exclude:
                if true, returns false for any structures with the specie
                (excludes them from the Transmuter)
        """
        self._species = map(smart_element_or_specie, species)
        self._strict = strict_compare
        self._AND = AND
        self._exclude = exclude

    def test(self, structure):
        #set up lists to compare
        if not self._strict:
            #compare by atomic number
            atomic_number = lambda x: x.Z
            filter_set = set(map(atomic_number, self._species))
            structure_set = set(map(atomic_number,
                                structure.composition.elements))
        else:
            #compare by specie or element object
            filter_set = set(self._species)
            structure_set = set(structure.composition.elements)

        if self._AND and filter_set <= structure_set:
            #return true if we aren't excluding since all are in structure
            return not self._exclude
        elif (not self._AND) and filter_set & structure_set:
            #return true if we aren't excluding since one is in structure
            return not self._exclude
        else:
            #return false if we aren't excluding otherwise
            return self._exclude

    def __repr__(self):
        return "\n".join(["ContainsSpecieFilter with parameters:",
                          "species = {}".format(self._species),
                          "strict_compare = {}".format(self._strict),
                          "AND = {}".format(self._AND),
                          "exclude = {}".format(self._exclude)])

    @property
    def to_dict(self):
        return {"version": __version__, "@module": self.__class__.__module__,
                "@class": self.__class__.__name__,
                "init_args": {"species": [str(sp) for sp in self._species],
                              "strict_compare": self._strict,
                              "AND": self._AND,
                              "exclude": self._exclude}}


class SpecieProximityFilter(AbstractStructureFilter):
    """
    This filter removes structures that have certain species that are too close
    together.
    """

    def __init__(self, specie_and_min_dist_dict):
        """
        Args:
            specie_and_min_dist_dict:
                A species string to float mapping. For example, {"Na+": 1}
                means that all Na+ ions must be at least 1 Angstrom away from
                each other. Multiple species criteria can be applied. Note that
                the testing is done based on the actual object. If you have a
                structure with Element, you must use {"Na":1} instead to filter
                based on Element and not Specie.
        """
        self.specie_and_min_dist = {smart_element_or_specie(k): v
                                    for k, v
                                    in specie_and_min_dist_dict.items()}

    def test(self, structure):
        all_species = set(self.specie_and_min_dist.keys())
        for site in structure:
            species = site.species_and_occu.keys()
            sp_to_test = set(species).intersection(all_species)
            if sp_to_test:
                max_r = max([self.specie_and_min_dist[sp]
                             for sp in sp_to_test])
                nn = structure.get_neighbors(site, max_r)
                for sp in sp_to_test:
                    for (nnsite, dist) in nn:
                        if sp in nnsite.species_and_occu.keys():
                            if dist < self.specie_and_min_dist[sp]:
                                return False
        return True

    @property
    def to_dict(self):
        return {"version": __version__, "@module": self.__class__.__module__,
                "@class": self.__class__.__name__,
                "init_args": {"specie_and_min_dist_dict":
                              {str(sp): v
                              for sp, v in self.specie_and_min_dist.items()}}}


class RemoveDuplicatesFilter(AbstractStructureFilter):
    """
    This filter removes exact duplicate structures from the transmuter.
    """

    def __init__(self, structure_matcher=StructureMatcher(
                 comparator=ElementComparator()), symprec=None):
        """
        Remove duplicate structures based on the structure matcher
        and symmetry (if symprec is given).

        Args:
            structure_matcher:
                Provides a structure matcher to be used for structure
                comparison.
            symprec:
                The precision in the symmetry finder algorithm
                if None (default value), no symmetry check is performed and
                only the structure matcher is used. A recommended value is 1e-5
        """
        self._symprec = symprec
        self._structure_list = []
        if isinstance(structure_matcher, dict):
            self._sm = StructureMatcher.from_dict(structure_matcher)
        else:
            self._sm = structure_matcher

    def test(self, structure):
        if not self._structure_list:
            self._structure_list.append(structure)
            return True

        def get_sg(s):
            finder = SymmetryFinder(s, symprec=self._symprec)
            return finder.get_spacegroup_number()

        for s in self._structure_list:
            if self._sm._comparator.get_structure_hash(structure) ==\
                    self._sm._comparator.get_structure_hash(s):
                if self._symprec is None or \
                        get_sg(s) == get_sg(structure):
                    if self._sm.fit(s, structure):
                        return False

        self._structure_list.append(structure)
        return True

    @property
    def to_dict(self):
        return {"version": __version__, "@module": self.__class__.__module__,
                "@class": self.__class__.__name__,
                "init_args": {"structure_matcher": self._sm.to_dict}}


class ChargeBalanceFilter(AbstractStructureFilter):
    """
     This filter removes structures that are not
     charge balanced from the transmuter.
     This only works if the structure is
     oxidation state decorated, as structures
     with only elemental sites are automatically
     assumed to have net charge of 0
    """
    def test(self, structure):
        if structure.charge == 0.0:
            return True
        else:
            return False

    @property
    def to_dict(self):
        return {"@module": self.__class__.__module__,
                "@class": self.__class__.__name__}
