"""Generate E3FP fingerprints.

Author: Seth Axen
E-mail: seth.axen@gmail.com
"""
from __future__ import division, print_function
import os
import logging
import argparse

from python_utilities.scripting import setup_logging
from python_utilities.parallel import make_data_iterator, Parallelizer, \
                                        ALL_PARALLEL_MODES
from python_utilities.io_tools import touch_dir
from e3fp.conformer.util import mol_from_sdf
from e3fp.fingerprint.fprinter import Fingerprinter
import e3fp.fingerprint.fprint as fp


def fprints_dict_from_sdf(sdf_file, **kwargs):
    try:
        mol = mol_from_sdf(sdf_file)
    except:
        logging.error("Error retrieving mol from %s." % (sdf_file))
        return False
    fprints_dict = fprints_dict_from_mol(mol, **kwargs)
    return fprints_dict


def fprints_dict_from_mol(mol, max_iters=-1, shell_radius=2.0, first=-1,
                          counts=False, stereo=False, out_dir_base="E3FP",
                          out_ext=".bz2", store_identifiers_map=False,
                          include_disconnected=True, overwrite=False,
                          save=True):
    """Build a E3FP fingerprint from a mol encoded in an SDF file.

    Parameters
    ----------
    sdf_file : str
        SDF file path.
    max_iters : int, optional (default -1)
        Maximum number of iterations/level of E3FP. -1 runs until termination.
    shell_radius : float, optional (default 2.0)
        Radius multiplier for spherical shells.
    first : int, optional (default -1)
        First N number of conformers from file to fingerprint. If -1, all are
        fingerprinted.
    counts : bool (default False)
        Instead of bit-based Fingerprint objects, generate count-based
        CountFingerprint objects.
    stereo : bool, optional (default False)
        Incorporate stereochemistry in fingerprint.
    out_dir_base : str, optional (default "E3FP")
        Basename of out directory to save fingerprints. Iteration number is
        appended.
    out_ext : str, optional (default ".bz2")
        Extension on fingerprint pickles, used to determine compression level.
    store_identifiers_map : bool, optional (default False)
        Within each fingerprint, store map from each identifier to
        corresponding substructure. Drastically increases size of fingerprint.
    include_disconnected : bool, optional (default True)
        Include disconnected atoms when hashing, but do use them for
        stereo calculations. Turn off purely for debugging, to make E3FP more
        like ECFP.
    overwrite : bool, optional (default False)
        Overwrite pre-existing file.
    """
    name = mol.GetProp("_Name")
    if save:
        filenames = []
        all_files_exist = True
        for i in xrange(max_iters + 1):
            dir_name = "%s%d" % (out_dir_base, i)
            touch_dir(dir_name)
            filename = "%s/%s%s" % (dir_name, name, out_ext)
            filenames.append(filename)
            if not os.path.isfile(filename):
                all_files_exist = False

        if all_files_exist and not overwrite:
            logging.warning("All fingerprint files for %s already exist. Skipping." % (name))
            return {}

    if max_iters is None:
        max_iters = -1
    fingerprinter = Fingerprinter(level=max_iters,
                                  radius_multiplier=shell_radius,
                                  counts=counts, stereo=stereo,
                                  store_identifiers_map=store_identifiers_map,
                                  include_disconnected=include_disconnected)

    fprints_dict = {}

    try:
        logging.info("Generating fingerprints for %s." % name)
        for j, conf in enumerate(mol.GetConformers()):
            if j == first:
                break
            fingerprinter.run(conf=conf)
            for i in xrange(max_iters + 1):
                fprint = fingerprinter.get_fingerprint_at_level(i)
                fprint.name = "%s_%d" % (name, j)
                fprints_dict.setdefault(i, []).append(fprint)
        logging.info("Generated %d fingerprints for %s." % (j, name))
    except Exception:
        logging.error("Error fingerprinting %s." % (name), exc_info=True)
        return {}

    if save:
        try:
            for i, fprints in sorted(fprints_dict.items()):
                fp.savez(filenames[i], *fprints)
            logging.info("Saved fingerprints for %s." % name)
        except Exception:
            logging.error(
                "Error saving fingerprints for %s to %s" % (name,
                                                            filenames[i]),
                exc_info=True)
            return {}

    return fprints_dict


def run(sdf_files, out_dir_base="E3FP", out_ext=".bz2", first=-1,
        max_iterations=-1, shell_radius=2.0, counts=False, stereo=False,
        store_identifiers_map=False, exclude_disconnected=False,
        overwrite=False, log=None, num_proc=None, parallel_mode=None,
        verbose=False):
    """Generate E3FP fingerprints from SDF files.

    Parameters
    ----------
    sdf_files : str
        Path to SDF file(s), each with one molecule and multiple conformers.
    out_dir_base : str, optional (default "E3FP")
        Basename for output directory to save fingerprints. Iteration number
        is appended to basename.
    out_ext : str, optional (default ".bz2")
        Extension for fingerprint pickles. Options are (".pkl", ".gz", ".bz2").
    first : int, optional (default -1)
        Maximum number of first conformers for which to generate fingerprints.
    max_iterations : int, optional (default -1)
        Maximum number of iterations for fingerprint generation.
    shell_radius : float, optional (default 2.0)
        Distance to increment shell radius at around each atom, starting at
        0.0.
    counts : bool, optional (default False)
        Store counts-based E3FC instead of default bit-based.
    stereo : bool, optional (default False)
        Differentiate by stereochemistry.
    store_identifiers_map : bool, optional (default False)
        Within each fingerprint, store map from "on" bits to each substructure
        represented.
    exclude_disconnected : bool, optional (default False)
        Exclude disconnected atoms when hashing, but do use them for
        stereo calculations. Included purely for debugging, to make E3FP more
        like ECFP.
    overwrite : bool, optional (default False)
        Overwrite existing file(s).
    log : str, optional (default None)
        Log filename.
    num_proc : int, optional (default None)
        Set number of processors to use.
    verbose : bool, optional (default False)
        Run with extra verbosity.
    """
    para = Parallelizer(num_proc=num_proc, parallel_mode=parallel_mode)

    setup_logging(log, verbose)

    if para.rank == 0:
        logging.info("Initializing E3FP generation.")
        logging.info("Getting SDF files")

        if len(sdf_files) == 1 and os.path.isdir(sdf_files[0]):
            from glob import glob
            sdf_files = glob("%s/*" % sdf_files[0])

        data_iterator = make_data_iterator(sdf_files)

        logging.info("SDF File Number: %d" % len(sdf_files))
        logging.info("Out Directory Basename: %s" % out_dir_base)
        logging.info("Out Extension: %s" % out_ext)
        logging.info("Max First Conformers: %d" % first)
        logging.info("Max Iteration Num: %d" % max_iterations)
        logging.info("Shell Radius Multiplier: %.4g" % shell_radius)
        logging.info("Stereo Mode: %s" % str(stereo))
        if para.is_mpi:
            logging.info("Parallel Mode: MPI")
        elif para.is_concurrent:
            logging.info("Parallel Mode: multiprocessing")
        else:
            logging.info("Parallel Mode: off")
        logging.info("Starting")
    else:
        data_iterator = iter([])

    fp_kwargs = {"first": int(first),
                 "max_iters": int(max_iterations),
                 "shell_radius": float(shell_radius),
                 "stereo": stereo,
                 "out_dir_base": out_dir_base,
                 "out_ext": out_ext,
                 "counts": counts,
                 "overwrite": overwrite,
                 "store_identifiers_map": store_identifiers_map,
                 "include_disconnected": not exclude_disconnected}

    run_kwargs = {
        "kwargs": fp_kwargs, "logging_str": "Generated fingerprints for %s",
        "logging_format": lambda x: os.path.basename(x[0]).split(os.extsep)[0]}

    para.run(fprints_dict_from_sdf, data_iterator, **run_kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        """Generate E3FP fingerprints from SDF files.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('sdf_files', nargs='+', type=str,
                        help="""Path to SDF file(s), each with one molecule
                             and multiple conformers.""")
    parser.add_argument('-o', '--out_dir_base', type=str,
                        default="E3FP",
                        help="""Basename for output directory to save
                             fingerprints. Iteration number is appended to
                             basename.""")
    parser.add_argument('--out_ext', type=str, default=".bz2",
                        choices=[".pkl", ".gz", ".bz2"],
                        help="""Extension for fingerprint pickles.""")
    parser.add_argument('--first', type=int, default=-1,
                        help="""Set maximum number of first conformers to
                             generare fingerprints for.""")
    parser.add_argument('-m', '--max_iterations', type=int, default=-1,
                        help="""Maximum number of iterations for fingerprint
                             generation.""")
    parser.add_argument('-r', '--shell_radius', type=float, default=2.0,
                        help="""Distance to increment shell radius at around
                             each atom, starting at 0.0.""")
    parser.add_argument('--counts', action='store_true',
                        help="""Store counts-based E3FC instead of default
                             bit-based.""")
    parser.add_argument('--stereo', action="store_true",
                        help="""Differentiate by stereochemistry.""")
    parser.add_argument('--store_identifiers_map', action="store_true",
                        help="""Within each fingerprint, store map from
                             "on" bits to each substructure represented.""")
    parser.add_argument('--exclude_disconnected', action="store_true",
                        help="""Include disconnected atoms when hashing, but
                        do use them for stereo calculations. Turn off purely
                        for debugging, to make E3FP more like ECFP.""")
    parser.add_argument('-O', '--overwrite', action="store_true",
                        help="""Overwrite existing file(s).""")
    parser.add_argument('-l', '--log', type=str, default=None,
                        help="Log filename.")
    parser.add_argument('-p', '--num_proc', type=int, default=None,
                        help="""Set number of processors to use.""")
    parser.add_argument('--parallel_mode', type=str, default=None,
                        choices=list(ALL_PARALLEL_MODES),
                        help="""Set parallelization mode to use.""")
    parser.add_argument('-v', '--verbose', action="store_true",
                        help="Run with extra verbosity.")
    params = parser.parse_args()

    kwargs = dict(params._get_kwargs())
    sdf_files = kwargs.pop('sdf_files')
    run(sdf_files, **kwargs)
