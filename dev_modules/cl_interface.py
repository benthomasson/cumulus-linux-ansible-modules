#!/usr/bin/env python
#
# Copyright (C) 2014, Cumulus Networks www.cumulusnetworks.com
#
#
DOCUMENTATION = '''
---
module: cl_interface
author: Stanley Karunditu
short_description: Configures a front panel , bridge or bond interface.
description:
    - Configures a front panel, management, loopback, bridge or bond interface.
options:
    name:
        description:
            - name of the interface
        required: true
    ipv4:
        description:
            - list of IPv4 addresses to configure on the interface. use CIDR
            syntax.
        default: None
    ipv6:
        description:
            - list of IPv6 addresses  to configure on the interface. use CIDR
            syntax
        default: None
    bridgemems:
        description:
            - list ports associated with the bridge interface.
        default: None
    bondmems:
        description:
            - list ports associated with the bond interface
        default: None
    applyconfig:
        description:
            - apply interface change
        choices: ['yes', 'no']
        default: 'no'


notes:
    - Cumulus Linux Interface Documentation - http://cumulusnetworks.com/docs/2.0/user-guide/layer_1_2/interfaces.html
    - Contact Cumulus Networks @ http://cumulusnetworks.com/contact/
'''
EXAMPLES = '''
#Example playbook entries using the cl_interface

## configure a front panel port with an IP
cl_interface: name=swp1  ipv4=10.1.1.1/24 apply=yes

## configure a front panel port with multiple IPs
cl_interface: name=swp1 ipv4=['10.1.1.1/24', '20.1.1.1/24'] apply=yes

## configure a bridge interface with a few trunk members and access port
cl_interface: name=br0  bridgemems=['swp1-10.100', 'swp11'] apply=yes

## configure a bond interface with an IP address
cl_interface: name=br0 bondmems=['swp1', 'swp2'] ipv4='10.1.1.1/24' apply=yes
'''


def run_cl_cmd(module, cmd):
    (rc, out, err) = module.run_command(cmd, check_rc=False)
    # trim last line as it is always empty
    ret = out.splitlines()
    return ret


def get_iface_type(module):
    if module.params.get('bridgemems'):
        return 'bridge'
    elif module.params.get('bondmems'):
        return 'bond'
    elif module.params.get('name') == 'lo':
        return 'loopback'
    elif re.match('^eth', module.params.get('name')):
        return 'mgmt'
    elif re.match('^swp', module.params.get('name')):
        return 'swp'
    else:
        _name = module.params.get('name')
        _msg = 'unable to determine interface type %s' % (_name)
        module.fail_json(msg=_msg)


def create_config_dict(iface):
    if 'config' not in iface:
        iface['config'] = {}


def create_config_addr_attr(iface):
    try:
        if 'address' not in iface['config']:
            iface['config']['address'] = None
    except:
        pass


def add_ipv4(module, iface):
    addrs = module.params.get('ipv4')
    if addrs:
        create_config_addr_attr(iface)
        iface['config']['address'] = addrs


def add_ipv6(module, iface):
    addrs = module.params.get('ipv6')
    if not addrs:
        return
    create_config_addr_attr(iface)
    addr_attr = iface['config']['address']
    if addr_attr is None:
        iface['config']['address'] = addrs
    elif isinstance(addr_attr, str):
        if isinstance(addrs, str):
            iface['config']['address'] = [addr_attr, addrs]
        elif isinstance(addrs, list):
            iface['config']['address'] = addrs + [addr_attr]
    elif isinstance(addr_attr, list):
        if isinstance(addrs, str):
            iface['config']['address'] = addr_attr + [addrs]
        elif isinstance(addrs, list):
            iface['config']['address'] = addr_attr + addrs


def config_changed(module, a_iface):
    if a_iface['ifacetype'] == 'loopback':
        a_iface['addr_method'] = 'loopback'
        a_iface['addr_family'] = 'inet'
    else:
        a_iface['addr_method'] = None
        a_iface['addr_family'] = None
    a_iface['auto'] = True
    a_iface = sortdict(a_iface)
    c_iface = None
    cmd = '/sbin/ifquery --format json %s' % (a_iface['name'])
    json_ifquery = run_cl_cmd(module, cmd)
    if len(json_ifquery) == 0:
        return True
    c_iface = sortdict(json.loads(''.join(json_ifquery))[0])
    a_iface_copy = copy.deepcopy(a_iface)
    del a_iface_copy['ifacetype']
    if a_iface_copy == c_iface:
        _msg = "no change in interface %s configuration" % (a_iface['name'])
        module.exit_json(msg=_msg, changed=False)
        return False
    else:
        return True


def apply_config(module, iface):
    cmd = '/sbin/ifup %s' % (iface['name'])
    run_cl_cmd(module, cmd)


def sortdict(od):
    res = {}
    for k, v in sorted(od.items()):
        if isinstance(v, dict):
            res[k] = sortdict(v)
        elif isinstance(v, list):
            res[k] = sorted(v)
        else:
            res[k] = v
    return res


def config_lo_iface(module, iface):
    add_ipv4(module, iface)
    add_ipv6(module, iface)


def config_swp_iface(module, iface):
    add_ipv4(module, iface)
    add_ipv6(module, iface)


def modify_switch_config(module, iface):
    filestr = "auto %s\n" % (iface['name'])
    if iface['ifacetype'] == 'loopback':
        filestr += "iface %s inet loopback\n" % (iface['name'])
    else:
        filestr += "iface %s\n" % (iface['name'])
    if 'config' in iface:
        for k, v in iface['config'].items():
            if isinstance(v, list):
                for subv in v:
                    filestr += "    %s %s\n" % (k, subv)
            else:
                filestr += "    %s %s\n" % (k, v)

    directory = '/etc/network/ansible/'
    if not os.path.exists(directory):
        os.makedirs(directory)
    filename = "/etc/network/ansible/%s" % (iface['name'])
    f = open(filename, 'w')
    f.write(filestr)
    f.close()


def remove_config_from_etc_net_interfaces(module, iface):
    try:
        f = open('/etc/network/interfaces', 'r')
    except:
        module.exit_json(msg="Unable to open /etc/network/interfaces")
        return

    config = f.readlines()
    new_config = []
    delete_line = False
    add_source_ansible = True

    for k, line in enumerate(config):
        matchstr = 'auto %s' % (iface['name'])
        matchstr2 = 'auto .*'
        match_iface_auto = re.match(matchstr, line)
        match_any_auto = re.match(matchstr2, line)
        match_ansible = re.match("source\s+/etc/network/ansible", line)
        if match_iface_auto:
            delete_line = True
        elif delete_line and match_any_auto:
            delete_line = False
        elif match_ansible:
            add_source_ansible = False
        if not delete_line:
            new_config.append(line)

    if add_source_ansible:
        addlines = ['\n',
                    '## Ansible controlled interfaces found here\n',
                    'source /etc/network/ansible/*\n']
        new_config = new_config + addlines

    f2 = open('/etc/network/interfaces', 'w')
    f2.writelines(new_config)
    f2.close()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            name=dict(required=True, type='str'),
            bridgemems=dict(default=None, type='list'),
            bondmems=dict(default=None, type='list'),
            ipv4=dict(default=None, type='list'),
            ipv6=dict(default=None, type='list'),
            applyconfig=dict(required=True, type='str')
        )
    )


    _ifacetype = get_iface_type(module)
    iface = {'ifacetype': _ifacetype}
    iface['name'] = module.params.get('name')
    create_config_dict(iface)
    if _ifacetype == 'loopback':
        config_lo_iface(module, iface)
    elif _ifacetype == 'swp':
        config_swp_iface(module, iface)
    config_changed(module, iface)
    modify_switch_config(module, iface)
    remove_config_from_etc_net_interfaces(module, iface)
    if module.params.get('applyconfig') == 'yes':
        apply_config(module, iface)
    _msg = 'interface successfully configured %s' % (iface['name'])
    module.exit_json(msg=_msg, changed=True)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.urls import *
import copy
import os

if __name__ == '__main__':
    main()
