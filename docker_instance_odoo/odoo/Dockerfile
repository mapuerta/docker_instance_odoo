FROM yoytec-odoo120:latest
COPY scripts/getaddons.py /home/odoo/getaddons.py
COPY scripts/entry_point.py /entry_point.py
RUN chmod +x /entry_point.py

VOLUME ["/var/log/supervisor", "/home/odoo/.local/share/Odoo", "/tmp", "/home/odoo/.ssh"]

## Expose xmlrpc and longpolling ports
EXPOSE 8069 8072

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/entry_point.py"]
