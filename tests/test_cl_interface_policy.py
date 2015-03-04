import mock
import os
from nose.tools import set_trace
import dev_modules.cl_interface_policy as cl_int_policy
from asserts import assert_equals

@mock.patch('dev_modules.cl_interface_policy.unconfigure_interfaces')
@mock.patch('dev_modules.cl_interface_policy.convert_allowed_list_to_port_range')
@mock.patch('dev_modules.cl_interface_policy.read_current_int_dir')
@mock.patch('dev_modules.cl_interface_policy.AnsibleModule')
def test_module_args(mock_module,
                     mock_read_current,
                     mock_allowed_range,
                     mock_unconfigure):
    """ cl_int_policy - Test module argument specs"""
    cl_int_policy.main()
    mock_module.assert_called_with(
        argument_spec={'allowed': {'type': 'list', 'required': True},
                       'location': {'type': 'str'}}
    )
