FROM yoytec-odoo120:latest
RUN chmod +x /entry_point.py

VOLUME ["/var/log/supervisor", "/home/odoo/.local/share/Odoo", "/tmp", "/home/odoo/.ssh"]

RUN branchesv pull -p /home/odoo/instance/extra_addons
RUN git clone https://github.com/OCA/maintainer-quality-tools.git ${HOME}/maintainer-quality-tools
RUN ${HOME}/maintainer-quality-tools/travis/clone_oca_dependencies /home/odoo/instance/extra_addons /home/odoo/instance/extra_addons
RUN python /home/odoo/getaddons.py /home/odoo/instance/extra_addons
## Expose xmlrpc and longpolling ports
EXPOSE 8069 8072

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/entry_point.py"]
