#!/usr/bin/env python
# coding: utf-8

import subprocess
import argparse
import tarfile
import zipfile
import tempfile
from os import path


parser = argparse.ArgumentParser()
parser.add_argument("-w", "--worker-dir", required=True, help="worker dir")
parser.add_argument("-f", "--file_yml", required=True, help="docker-compose.yml")
parser.add_argument("--restoredb", action='append', help="Restore backup")
parser.add_argument("--update", help="Update instance", action="store_true")
parser.add_argument("--rebuild", help="Rebuild instance", action="store_true")
parser.add_argument("-d", "--dbname", type=str, help="Database name")
parser.add_argument("-s", "--dbhost", type=str, help="Server postgresql")
args = parser.parse_args()


def _spawn(cmd):
    cmd = " ".join(cmd)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
    out, err = p.communicate()
    print(out)

def tar_name_list(fobject):
    values = []
    if isinstance(fobject, tarfile.TarFile):
        values = [i.name for i in fobject.getmembers()]
    if isinstance(fobject, zipfile.ZipFile):
        values = fobject.namelist()
    return values
        

def support_method():
    extract = lambda cmd: subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    ext_methods = {
        "gz": lambda filename, dsc_dir: extract([
            'tar', '-zxvf', filename,
            '--strip-components=1', '-C', dsc_dir]),
        "zip": lambda filename, dsc_dir: extract([
            'unzip', filename, '-d', dsc_dir]),
        "bz2": lambda filename, dsc_dir: extract([
            'tar', '-xjvf', filename,
            '--strip-components=1', '-C', dsc_dir]),
    }
    return ext_methods


def compress_open_file(filename, ext):
    ext_open = {
        "zip": zipfile.ZipFile.open,
        "bz2": tarfile.open,
        "gz": tarfile.open,
    }
    return ext_open[ext](filename, 'r:'+ext)


def extrac_file(filename, dest_folder):
    result = False
    support_method = support_method()
    for ext, method in support_method.items():
        if filename.endswith(ext):
            result = compress_open_file(filename, 'r:'+ext)
            method(filename, dest_folder)
    return tar_name_list(result)


def rebuild_instance():
    cmd1 = ['docker-compose', '-f', args.file_yml, 'down']
    cmd2 = ['docker-compose', '-f', args.file_yml, 'up', '-d', '--build', '--scale', 'odoo=3']
    for cmd in [cmd1, cmd2]:
        _spawn(cmd)


def update_instance():
    cmd_odoo = '/home/odoo/instance/odoo/odoo-bin -c /mnt/odoo.conf -u all --stop-after-init'
    cmd1 = ['docker-compose', '-f', args.file_yml, 'down']
    cmd2 = ['docker-compose', '-f', args.file_yml, 'up', '-d']
    cmd3 = ['docker-compose', '-f', args.file_yml, 'exec', 'odoo', 'supervisorctl stop odoo']
    cmd4 = ['docker-compose', '-f', args.file_yml, 'exec', '-u', 'odoo', 'odoo', cmd_odoo]
    cmd5 = ['docker-compose', '-f', args.file_yml, 'exec', 'odoo', 'supervisorctl start odoo']
    cmd6 = ['docker-compose', '-f', args.file_yml, 'up', '-d', '--scale', 'odoo=3']
    for cmd in [cmd1, cmd2, cmd3, cmd4, cmd5, cmd6]:
        _spawn(cmd)


def restore_db(self):
    tmp_path = tempfile.TemporaryDirectory().name
    cmd1 = ['docker-compose', '-f', args.file_yml, 'stop', 'odoo']
    file_descompress = extrac_file(args.restoredb, tmp_path)
    file_sql = [path.basename(i) for i in file_descompress if i.endswith('.sql')]
    file_sql = file_sql and file_sql[0] or 'database_dump.sql'
    file_sql = path.join(tmp_path, file_sql)
    file_store = path.join(tmp_path, filestore)
    filestore_path = path.join(args.worker_dir, 'filestore')
    cmd2 = ['dropdb', '-h', args.dbhost, '-u', 'odoo', args.dbname]
    cmd3 = ['psql', '-h', args.dbhost, '-d', args.dbname, '-f', file_sql, '-u', 'odoo']
    cmd4 = ['cp', '-rf', file_store, filestore_path]
    cmd5 = ['docker-compose', '-f', args.file_yml, 'start', 'odoo']
    for cmd in [cmd1, cmd2, cmd3, cmd4, cmd5]:
        _spawn(cmd)
    update_instance()


if args.update:
    update_instance()

if args.restoredb:
    restore_db()

if args.rebuild:
    rebuild_instance()
