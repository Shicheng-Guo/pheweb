
'''
This script creates json files which can be used to render Manhattan plots.
'''

# TODO: combine with QQ.

from ..utils import conf, chrom_order, get_phenolist
from ..file_utils import VariantFileReader, write_json, common_filepaths
from .load_utils import MaxPriorityQueue, star_kwargs, exception_printer, get_num_procs

import os
import math
import datetime
import multiprocessing


def rounded_neglog10(pval, neglog10_pval_bin_size, neglog10_pval_bin_digits):
    return round(-math.log10(pval) // neglog10_pval_bin_size * neglog10_pval_bin_size, neglog10_pval_bin_digits)


def get_pvals_and_pval_extents(pvals, neglog10_pval_bin_size):
    # expects that NEGLOG10_PVAL_BIN_SIZE is the distance between adjacent bins.
    pvals = sorted(pvals)
    extents = [[pvals[0], pvals[0]]]
    for p in pvals:
        if extents[-1][1] + neglog10_pval_bin_size * 1.1 > p:
            extents[-1][1] = p
        else:
            extents.append([p,p])
    rv_pvals, rv_pval_extents = [], []
    for (start, end) in extents:
        if start == end:
            rv_pvals.append(start)
        else:
            rv_pval_extents.append([start,end])
    return (rv_pvals, rv_pval_extents)


# TODO: convert bins from {(chrom, pos): []} to {chrom:{pos:[]}}?
def bin_variants(variant_iterator, bin_length, n_unbinned, neglog10_pval_bin_size, neglog10_pval_bin_digits):
    bins = {}
    unbinned_variant_pq = MaxPriorityQueue()
    chrom_n_bins = {}

    def bin_variant(variant):
        chrom_key = chrom_order[variant['chrom']]
        pos_bin = variant['pos'] // bin_length
        chrom_n_bins[chrom_key] = max(chrom_n_bins.get(chrom_key,0), pos_bin)
        if (chrom_key, pos_bin) in bins:
            bin = bins[(chrom_key, pos_bin)]

        else:
            bin = {"chrom": variant['chrom'],
                   "startpos": pos_bin * bin_length,
                   "neglog10_pvals": set()}
            bins[(chrom_key, pos_bin)] = bin
        bin["neglog10_pvals"].add(rounded_neglog10(variant['pval'], neglog10_pval_bin_size, neglog10_pval_bin_digits))

    # put most-significant variants into the priorityqueue and bin the rest
    for variant in variant_iterator:
        unbinned_variant_pq.add(variant, variant['pval'])
        if len(unbinned_variant_pq) > n_unbinned:
            old = unbinned_variant_pq.pop()
            bin_variant(old)

    unbinned_variants = list(unbinned_variant_pq.pop_all())

    # unroll bins into simple array (preserving chromosomal order)
    binned_variants = []
    for chrom_key in sorted(chrom_n_bins.keys()):
        for pos_key in range(int(1+chrom_n_bins[chrom_key])):
            b = bins.get((chrom_key, pos_key), None)
            if b and len(b['neglog10_pvals']) != 0:
                b['neglog10_pvals'], b['neglog10_pval_extents'] = get_pvals_and_pval_extents(b['neglog10_pvals'], neglog10_pval_bin_size)
                b['pos'] = int(b['startpos'] + bin_length/2)
                del b['startpos']
                binned_variants.append(b)

    return binned_variants, unbinned_variants


MASK_AROUND_PEAK = int(500e3)
def label_peaks(variants):
    chroms = {}
    for v in variants:
        chroms.setdefault(v['chrom'], []).append(v)
    for vs in chroms.values():
        while vs:
            best_assoc = min(vs, key=lambda assoc: assoc['pval'])
            best_assoc['peak'] = True
            vs = [v for v in vs if abs(v['pos'] - best_assoc['pos']) > MASK_AROUND_PEAK]


@exception_printer
@star_kwargs
def make_json_file(src_filepath, dest_filepath):

    BIN_LENGTH = int(3e6)
    NEGLOG10_PVAL_BIN_SIZE = 0.05 # Use 0.05, 0.1, 0.15, etc
    NEGLOG10_PVAL_BIN_DIGITS = 2 # Then round to this many digits
    N_UNBINNED = 2000

    if conf.debug: print('{}\t{} -> {} (START)'.format(datetime.datetime.now(), src_filepath, dest_filepath))
    with VariantFileReader(src_filepath) as variants:
        if conf.debug: print('{}\tOPENED {}'.format(datetime.datetime.now(), src_filepath))
        variant_bins, unbinned_variants = bin_variants(
            variants, BIN_LENGTH, N_UNBINNED, NEGLOG10_PVAL_BIN_SIZE, NEGLOG10_PVAL_BIN_DIGITS)
        if conf.debug: print('{}\tBINNED VARIANTS'.format(datetime.datetime.now()))
    if conf.debug: print('{}\tCLOSED FILE'.format(datetime.datetime.now()))
    label_peaks(unbinned_variants)
    rv = {
        'variant_bins': variant_bins,
        'unbinned_variants': unbinned_variants,
    }

    write_json(filepath=dest_filepath, data=rv)
    print('{}\t{} -> {}'.format(datetime.datetime.now(), src_filepath, dest_filepath))


def get_conversions_to_do():
    phenocodes = [pheno['phenocode'] for pheno in get_phenolist()]
    for phenocode in phenocodes:
        src_filepath = common_filepaths['pheno'](phenocode)
        dest_filepath = common_filepaths['manhattan'](phenocode)
        if not os.path.exists(dest_filepath) or os.stat(dest_filepath).st_mtime < os.stat(src_filepath).st_mtime:
            yield {
                'src_filepath': src_filepath,
                'dest_filepath': dest_filepath,
            }


def run(argv):

    conversions_to_do = list(get_conversions_to_do())
    print('number of phenos to process:', len(conversions_to_do))
    if conf.debug:
        for c in conversions_to_do:
            make_json_file(c)
    else:
        with multiprocessing.Pool(get_num_procs()) as p:
            p.map(make_json_file, conversions_to_do)
