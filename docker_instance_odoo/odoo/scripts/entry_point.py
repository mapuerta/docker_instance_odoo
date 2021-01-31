#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Entry point for Dockerized Odoo instances, we keep launching Odoo with supervisor
for backward compatibility, but the instances that are running in a multi-container environment
should be executed calling the Odoo binary directly
"""

import argparse
import fileinput
import logging
from os import stat, path, getenv, environ, setgid, setuid
import pwd
import random
import re
import shlex
from shutil import copy2
import string
from subprocess import call
import sys


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)-5s - %(name)s.%(funcName)s - %(message)s")

logger = logging.getLogger("entry_point")

USER_NAME = getenv('ODOO_USER') and getenv('ODOO_USER') or 'odoo'

FILESTORE_PATH = getenv('ODOO_FILESTORE_PATH') \
    and getenv('ODOO_FILESTORE_PATH') \
    or '/home/%s/.local/share/Odoo/filestore' % USER_NAME

CONFIGFILE_PATH = getenv('ODOO_CONFIG_FILE') \
    and getenv('ODOO_CONFIG_FILE') \
    or '/home/%s/.openerp_serverrc' % USER_NAME


def change_values(file_name, getter_func):
    """
    Changes value from a config file, new values are gotten from redis server
    or env vars

    :param str file_name: Config file name
    :param getter_func: Function that will be used for getting new values
    """
    logger.warning("Deprecation warning: please use ODOORC_ prefixed env vars to change odoo configuration")
    for line in fileinput.input(file_name, inplace=True):
        new_str = line
        logger.debug("Line readed: %s", line.strip())
        parts = line.split("=")
        if len(parts) > 1:
            search_str = parts[0].upper().strip()
            value = getter_func(search_str)
            logger.debug("Search for: %s and value is: %s", search_str, value)
            if search_str == 'ADMIN_PASSWD' and \
               (not value or value == 'admin'):
                value = ''.join(random.choice(string.letters+string.digits) for _ in range(12))
            if value:
                new_str = "%s = %s" % (parts[0].strip(), value.strip())
        print(new_str.replace('\n', ''))


def get_odoo_vars(getter_func, prefix="ODOORC_"):
    """
    Gets the variables using the getter_func, filter them by prefix and returns a dict with the proper values.
    The getter_func should be a function that gets the values from whatever source is configured to and return them
    as a dict.
    :param getter_func: Function that will be used for getting new values, this should return a dict
    in the following format:
        {
          "ODOORC_VARIABLE_NAME": 123,
          "ODOORC_ANOTHER_VARIABLE_NAME": "asd"
        }
    :param prefix: Prefix used to get the variables that will be used for Odoo configuration
    :return: A dict with the parms as keys, lowercase, without the prefix and
    ready to compare or append to the Odoo configuration file
    """
    p = prefix.lower()
    res = {}
    r = re.compile("^"+p)
    for key, value in getter_func():
        k = key.lower()
        if k.startswith(p):
            var = r.sub("", k, 1)
            res.update({var: value.strip()})
    return res


def update_sentry(config, getter_func):
    if config.get('sentry_enabled', False):
        config.update({
            'sentry_odoo_dir': '/home/odoo/instance/odoo',
            'sentry_environment': getter_func('INSTANCE_TYPE', 'develop')
        })
    return config


def append_values(file_name, getter_func, environ_items):
    """
    Append values to a config file, new values are gotten from env vars. All the variables must start with ODOORC_
    otherwise will be ignored (so we make sure not to append all variables)

    :param str file_name: Config file name
    :param getter_func: Function that will be used for getting new values, this should return a dict
    in the following format:
        {
          "ODOORC_VARIABLE_NAME": 123,
          "ODOORC_ANOTHER_VARIABLE_NAME": "asd"
        }
    :param environ_items: result of environ.items or list of environment values to use
    """
    variables = get_odoo_vars(environ_items)
    variables = update_sentry(variables, getter_func)

    for line in fileinput.input(file_name, inplace=True):
        new_str = line
        logger.debug("Line read: %s", line.strip())
        parts = line.split("=")
        logger.debug("Parts: %s", len(parts))
        if len(parts) > 1:
            search_str = parts[0].strip()
            value = variables.get(search_str, None)
            if search_str == 'ADMIN_PASSWD' and \
               (not value or value == 'admin'):
                value = ''.join(random.choice(string.letters+string.digits) for _ in range(12))
            if value is not None:
                del variables[search_str]
                new_str = "%s = %s" % (parts[0].strip(), value.strip())
        print(new_str.replace('\n', ''))

    with open(file_name, "a") as config:
        for key in variables:
            value = variables[key]
            new_str = "%s = %s" % (key, value)
            logger.debug("Appending : %s ", new_str)
            config.write(new_str + "\n")


def get_owner(file_name):
    """
    This function gets owner name from system for a directory or file

    :param str file_name: File or directory name
    :returns: Owner name
    """
    file_stat = stat(file_name)
    try:
        owner = pwd.getpwuid(file_stat.st_uid).pw_name
    except KeyError:
        owner = "None"
    logger.debug("Owner of %s is %s", file_name, owner)
    return owner


def check_container_type():
    """ Changes the configuration in case the instance is supposed to be a multi-container deployment. This
    was done following the official documentation:
    https://www.odoo.com/documentation/11.0/setup/deploy.html#odoo-as-a-wsgi-application

    """
    container_config = {
        'worker': {
            'odoorc_http_enable': True,
            'odoorc_max_cron_threads': 0,
            'odoorc_workers': 0,
            'odoorc_xmlrpcs': False,
        },
        'cron': {
            'odoorc_http_enable': False,
            'odoorc_max_cron_threads': 1,
            'odoorc_workers': 0,
            'odoorc_xmlrpc': False,
            'odoorc_xmlrpcs': False,
        },
        'longpoll': {
            'odoorc_http_enable': False,
            'odoorc_max_cron_threads': 0,
            'odoorc_workers': getenv('WORKERS', 2),
            'odoorc_xmlrpcs': False,
        }
    }
    ctype = getenv('CONTAINER_TYPE', 'NORMAL').lower()
    logger.info('Container type: %s', ctype)
    if ctype in container_config:
        for config, value in container_config.get(ctype).items():
            environ[config.upper()] = str(value)


def prepare(args):
    """
    Function to prepare the container and odoo configuration before running the requested command

    :param args: args parsed by argparse
    """
    chmod_cmds = [
        "chmod ugo+rwxt /tmp",
        "chmod ugo+rw /var/log/supervisor",
        "chown odoo:odoo /home/odoo/.local/share/Odoo",
        "chown odoo:odoo /home/odoo/.local/share/Odoo/filestore",
        "chown -R odoo:odoo /home/odoo/.ssh"
    ]

    logger.info("Preparing files")
    if not path.isfile(CONFIGFILE_PATH):
        copy2("/external_files/openerp_serverrc", CONFIGFILE_PATH)

    getter_func = getenv
    logger.info("Using env vars")

    check_container_type()
    change_values(CONFIGFILE_PATH, getter_func)
    append_values(CONFIGFILE_PATH, getter_func, environ.items)
    if not path.exists(FILESTORE_PATH):
        call(["mkdir", "-p", FILESTORE_PATH])

    logger.info("Setting permissions")

    for chmod in chmod_cmds:
        call(shlex.split(chmod))


def demote(user_uid, user_gid):
    """Pass the function 'set_ids' to preexec_fn, rather than just calling
    setuid and setgid. This will change the ids for that subprocess only"""

    def set_ids():
        setgid(user_gid)
        setuid(user_uid)

    return set_ids


def run_cmd_as(cmd, user, env=None):
    """
    Execute a command as a given user
    :param cmd: A string with the command to be executed
    :param user: Run the command as user
    :param env: The environment to be set for the command
    :return:
    """
    uid = pwd.getpwnam(user).pw_uid
    gid = pwd.getpwnam(user).pw_gid
    call(shlex.split(cmd), preexec_fn=demote(uid, gid), env=env)


def start(args):
    """
    Main entry point function, this will start supervisor
    :param args: the result from argparse
    """
    logger.info("All changes made, now will run supervisord")
    call(["supervisord", "-c", "/etc/supervisor/supervisord.conf"])


def run_cmd(args):
    """
    Just execute the received command (can be bash, odoo command like update, etc)
    :param args: the result from argparse
    """
    logger.info("All changes made, now will run the command")
    cmd = args.command[0]
    logger.debug(str(args.command))
    run_cmd_as(cmd, args.user)


def run_cou(args):
    """
    Execute click-odoo-update to update the database
    :param args: the result from argparse
    """
    logger.info("Staring click-odoo-update")
    cmd = "click-odoo-update -c {cfg} --logfile /tmp/deployvlogs/cou_update.log"
    if args.db_name:
        cmd += ' -d {db_name}'
    cmd = cmd.format(
        cfg=CONFIGFILE_PATH,
        db_name=args.db_name)
    env = environ.copy()
    env["PYTHONPATH"] = "/home/odoo/instance/odoo:" + env.get("PYTHONPATH", "")
    run_cmd_as(cmd, 'odoo', env)


if __name__ == '__main__':
    # This is a hack to make it compatible with p2
    # it don't like the default neither required false
    if len(sys.argv) < 2:
        sys.argv.append('start')
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(help='commands', dest='cmd')
    subparsers.required = False
    subparsers.default = 'start'
    run_parser = subparsers.add_parser('run', help='Run a command in bash')
    run_parser.add_argument('command', type=str, nargs='+', help='Command to be executed')
    run_parser.add_argument('--user', '-u', type=str,
                            help='User to run the command', default='root')
    run_parser.set_defaults(func=run_cmd)

    start_parser = subparsers.add_parser('start', help='Start the instance')
    start_parser.set_defaults(func=start)

    cou_parser = subparsers.add_parser('cou', help='Update database using click-odoo-update')
    cou_parser.add_argument('--db_name', '-d', type=str,
                            help=('Database name, if no db is provided'
                                  'will use the one in the config file'),
                            required=False)
    cou_parser.set_defaults(func=run_cou)

    args = parser.parse_args(sys.argv[1:])
    prepare(args)
    args.func(args)
