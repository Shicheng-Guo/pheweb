#!/usr/bin/env python2

from __future__ import print_function, division, absolute_import
import psycopg2
import csv
import json


print("Before this script, please run `psql -U pheweb_writer -d postgres -h localhost < schema.sql` to purge the database")

epacts_filename_template = '/net/dumbo/home/larsf/PheWAS/MATCHED/PheWAS_{}_MATCHED.epacts'


# phenos
with open('/net/dumbo/home/larsf/PheWAS/PheWAS_code_v1_2.txt') as f:
    phenos = {pheno['phewas_code2']: pheno for pheno in csv.DictReader(f, delimiter='\t')}

# icd9
with open('/net/dumbo/home/larsf/PheWAS/PheWAS_code_translation_v1_2.txt') as f:
    for icd9 in csv.DictReader(f, delimiter='\t'):
        phewas_code = icd9['phewas_code']
        if phewas_code in phenos:
            phenos[phewas_code].setdefault('icd9_info', []).append({'code': icd9['icd9'], 'string': icd9['icd9_string']})

with open('postgres_password') as f:
    postgres_password = f.read()
with psycopg2.connect(dbname="postgres", user="pheweb_writer", password=postgres_password, host="localhost") as conn:
    with conn.cursor() as curs:

        # Insert variants
        pheno = phenos.values()[0]
        with open(epacts_filename_template.format(pheno['NR'])) as f:
            for result in csv.DictReader(f, delimiter='\t'):
                ref, alt = result['MARKER_ID'].split('_')[1].split('/')
                curs.execute("INSERT INTO pheweb.variants (chromosome, position, ref, alt, name, rsids) "
                             "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                             (result['#CHROM'],
                              int(result['BEGIN']),
                              ref,
                              alt,
                              result['MARKER_ID'], # TODO: pretty this up
                              '[]', # TODO: get rsids
                          ))
        curs.execute('CREATE INDEX idx_variant_name ON pheweb.variants (name);')
        print('indexed')

        for category in set(pheno['category_string'] for pheno in phenos.itervalues()):
            curs.execute("INSERT INTO pheweb.categories (name) VALUES (%s) RETURNING id;",
                                       (category,))

        for pheno in phenos.itervalues():
            print(pheno['category_string'], '-', pheno['phewas_string'])

            # insert new pheno
            curs.execute("INSERT INTO pheweb.phenos (category_id, icd9_info, phewas_code, phewas_string, num_cases, num_controls) "
                         "VALUES ((SELECT id FROM pheweb.categories WHERE name = %s), %s, %s, %s, %s, %s) RETURNING id;",
                         (pheno['category_string'],
                          json.dumps(pheno['icd9_info']),
                          pheno['phewas_code2'],
                          pheno['phewas_string'],
                          pheno['Cases'],
                          pheno['Controls'],
                      ))
            pheno_id = curs.fetchone()[0]

            # insert all results for this pheno
            with open(epacts_filename_template.format(pheno['NR'])) as f:
                for result in csv.DictReader(f, delimiter='\t'):
                    if result['PVALUE'] != 'NA':
                        curs.execute("INSERT INTO pheweb.results (variant_id, pheno_id, beta, sebeta, maf, pval) "
                                     "VALUES ((SELECT id FROM pheweb.variants WHERE name = %s), %s, %s, %s, %s, %s) RETURNING id;",
                                     (result['MARKER_ID'],
                                      pheno_id,
                                      result['BETA'],
                                      result['SEBETA'],
                                      result['MAF'],
                                      result['PVALUE'],
                                  ))
