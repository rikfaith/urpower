#!/usr/bin/env python3
# urpower.py -*-python-*-

# Standard imports
import configparser
import os
import subprocess
import sys
import time

# Imports that might have to be installed
try:
    import pyghmi.ipmi.command
except ImportError as e:
    print('''\
# Cannot load pyghmi: {}
# Consider: apt-get install python3-pyghmi'''.format(e))
    raise SystemExit

try:
    import pysnmp.hlapi
except ImportError as e:
    print('''\
# Cannot load pysnmp: {}
# Consider: apt-get install python3-pysnmp4'''.format(e))
    raise SystemExit

#from pysnmp import debug
#debug.setLogger(debug.Debug('all'))


class UrPower(object):
    def __init__(self, debug=False):
        self.debug = debug
        self.config = configparser.ConfigParser()
        self.config.read(os.path.expanduser('~/.urpower'))
        self.oid_on_off = None
        self.cmd = None
        self.saved_session = None

    def _get_cmd(self, pdu, oid):
        errorIndication, errorStatus, errorIndex, varBinds = next(
            pysnmp.hlapi.getCmd(
                pysnmp.hlapi.SnmpEngine(),
                pysnmp.hlapi.CommunityData('public', mpModel=0),
                pysnmp.hlapi.UdpTransportTarget((pdu, 161)),
                pysnmp.hlapi.ContextData(),
                pysnmp.hlapi.ObjectType(
                    pysnmp.hlapi.ObjectIdentity(oid))))
        if errorIndication:
            print(errorIndication)
            return None
        elif errorStatus:
            print('{} at {}'.format(
                errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            return None
        return varBinds[0][1]

    def _set_cmd(self, pdu, oid, value):
        errorIndication, errorStatus, errorIndex, varBinds = next(
            pysnmp.hlapi.setCmd(
                pysnmp.hlapi.SnmpEngine(),
                pysnmp.hlapi.CommunityData('private', mpModel=0),
                pysnmp.hlapi.UdpTransportTarget((pdu, 161)),
                pysnmp.hlapi.ContextData(),
                pysnmp.hlapi.ObjectType(pysnmp.hlapi.ObjectIdentity(oid),
                                        pysnmp.hlapi.Integer32(value))))
        if errorIndication:
            print(errorIndication)
            return None
        elif errorStatus:
            print('{} at {}'.format(
                errorStatus.prettyPrint(),
                errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            return None
        return varBinds[0][1]

    def _pdu_name(self, pdu):
        return str(self._get_cmd(pdu, '1.3.6.1.2.1.1.1.0'))

    def _get_oid_on_off(self, pdu):
        name = self._pdu_name(pdu)
        if name is None:
            print('Cannot determine PDU type for {}'.format(pdu))
            return None
        self.oid_on_off = None
        if name.startswith('CPS Power Distributed Unit'):
            self.oid_on_off = ('1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4', 1, 2)
        if name.startswith('APC Switched Rack PDU'):
            self.oid_on_off = ('1.3.6.1.4.1.318.1.1.12.3.3.1.1.4', 1, 2)
        return self.oid_on_off

    def _get_pdu_outlet(self, host):
        if host not in self.config:
            print('No configuration information for {}'.format(host))
            return None
        if 'pdu' not in self.config[host]:
            print('No "pdu" specified for {}'.format(host))
            return None
        if 'outlet' not in self.config[host]:
            print('No "outlet" specified for {}'.format(host))
            return None

        pdu = self.config[host]['pdu']
        outlet = self.config[host]['outlet']
        return pdu, outlet

    def _print_status(self, host, pdu, outlet, status, onvalue, offvalue,
                      ipmi_power_state=None):
        if status == onvalue:
            pdu_state = 'on'
        elif status == offvalue:
            pdu_state = 'off'
        else:
            pdu_state = 'status={}'.format(status)

        print('host={} pdu={} outlet={} pdu_state={} ipmi_state={}'.format(
            host, pdu, outlet, pdu_state,
            ipmi_power_state if ipmi_power_state is not None else 'none'))

    def _has_ipmi_session(self, host):
        if host not in self.config or \
           'ipmi_host' not in self.config[host] or \
           'ipmi_username' not in self.config[host] or \
           'ipmi_password' not in self.config[host]:
            return False
        return True

    def _get_ipmi_session(self, host):
        # See https://stackoverflow.com/questions/66637872
        # Apparently we can only open one session, so we have to reuse it.
        if self.saved_session is not None:
            return self.saved_session

        if not self._has_ipmi_session(host):
            print('host={}'.format(host))
            if host in self.config:
                print('self.config[host]=', self.config[host])
            return None

        session = None
        ipmi_host = self.config[host]['ipmi_host']
        ipmi_username = self.config[host]['ipmi_username']
        ipmi_password = self.config[host]['ipmi_password']
        try:
            session = pyghmi.ipmi.command.Command(ipmi_host,
                                                  ipmi_username,
                                                  ipmi_password)
        except:
            print('Cannot open session host={} ipmi_host={} ipmi_username={}'.
                  format(host, ipmi_host, ipmi_username))
            return None
        self.saved_session = session
        return session

    def _get_ipmi_power_state(self, ipmi_session):
        status = ipmi_session.get_power()
        try:
            status = ipmi_session.get_power()
            return status['powerstate']
        except:
            return '?'

    def _set_ipmi_power_state(self, ipmi_session, state):
        try:
            status = ipmi_session.set_power(state, wait=False)
            return status['pendingpowerstate']
        except:
            return '?'

    def status(self, host):
        pdu_outlet = self._get_pdu_outlet(host)
        if pdu_outlet is None:
            return
        pdu, outlet = pdu_outlet
        oid_on_off = self._get_oid_on_off(pdu)
        if oid_on_off is None:
            return
        oid, onvalue, offvalue = oid_on_off
        status = self._get_cmd(pdu, oid + '.' + str(outlet))

        ipmi_power_state = None
        ipmi_session = self._get_ipmi_session(host)
        if ipmi_session is not None:
            ipmi_power_state = self._get_ipmi_power_state(ipmi_session)
        self._print_status(host, pdu, outlet, status, onvalue, offvalue,
                           ipmi_power_state)

    def _get_pdu_state(self, host):
        pdu_outlet = self._get_pdu_outlet(host)
        if not pdu_outlet:
            return 'NoPDU', None, None
        pdu, outlet = pdu_outlet
        oid_on_off = self._get_oid_on_off(pdu)
        if oid_on_off is None:
            return 'UnknownPDU', pdu, outlet
        oid, onvalue, offvalue = oid_on_off
        status = self._get_cmd(pdu, oid + '.' + str(outlet))
        if status == onvalue:
            return 'on', pdu, outlet
        elif status == offvalue:
            return 'off', pdu, outlet
        return status, pdu, outlet

    def _ping(self, host):
        result = subprocess.run(['ping', '-c', '1', '-W', '1', host],
                                timeout=2,
                                capture_output=True)
        return result.returncode == 0

    def _wait_for_ping(self, host, count=10):
        n = 0
        while n < count:
            if self._ping(host):
                print('  Successful ping from {}'.format(host))
                return True
            print('  Cannot ping {}, sleeping...'.format(host))
            time.sleep(10)
            n += 1
        return False

    def _power_on_via_ipmi(self, host):
        ipmi_host = self.config[host]['ipmi_host']
        self._wait_for_ping(ipmi_host)
        print('Getting IPMI session from {}'.format(ipmi_host))
        ipmi_session = self._get_ipmi_session(host)
        if ipmi_session is None:
            print('  Cannot get IPMI session')
            return None
        ipmi_power_state = self._get_ipmi_power_state(ipmi_session)
        print('  Found ipmi_power_state={}'.format(
            ipmi_power_state if ipmi_power_state is not None else 'none'))
        if ipmi_power_state != 'on':
            print('  Trying set ipmi_power_state=on')
            ipmi_power_state = self._set_ipmi_power_state(ipmi_session, 'on')
            print('  Found ipmi_power_state={}'.format(
                ipmi_power_state if ipmi_power_state is not None else 'none'))
        return ipmi_power_state

    def power_on(self, host):
        pdu_on = False
        pdu_state, pdu, outlet = self._get_pdu_state(host)
        if pdu_state == 'off':
            oid, onvalue, offvalue = self._get_oid_on_off(pdu)
            print('Turning on pdu={} outlet={}'.format(pdu, outlet))
            status = self._set_cmd(pdu, oid + '.' + str(outlet), int(onvalue))
            pdu_state, _, _ = self._get_pdu_state(host)
            if pdu_state == 'on':
                pdu_on = True
                print('Success: pdu={} outlet={}'.format(pdu, outlet))
            else:
                print('Error: pdu={} outlet={} pdu_state={} raw_status={}'.
                      format(pdu, outlet, pdu_state, status))
                return
        else:
            print('PDU already on: pdu={} outlet={} pdu_state={}'.format(
                pdu, outlet, pdu_state))

        ipmi_power_state = None
        if self._has_ipmi_session(host):
            ipmi_power_state = self._power_on_via_ipmi(host)
        print('host={} pdu={} outlet={} pdu_state={} ipmi_state={}'.format(
            host, pdu, outlet, pdu_state,
            ipmi_power_state if ipmi_power_state is not None else 'none'))
        self._wait_for_ping(host)

    def power_off(self, host):
        pdu_on = False
        pdu_state, pdu, outlet = self._get_pdu_state(host)
        if pdu_state == 'off':
            print('PDU already off: pdu={} outlet={} pdu_state={}'.format(
                pdu, outlet, pdu_state))
        else:
            oid, onvalue, offvalue = self._get_oid_on_off(pdu)
            print('Turning off pdu={} outlet={}'.format(pdu, outlet))
            status = self._set_cmd(pdu, oid + '.' + str(outlet), int(offvalue))
            pdu_state, _, _ = self._get_pdu_state(host)
            if pdu_state == 'off':
                print('Success: pdu={} outlet={}'.format(pdu, outlet))
            else:
                print('Error: pdu={} outlet={} pdu_state={} raw_status={}'.
                      format(pdu, outlet, pdu_state, status))
                return

    def set_state(self, host, on_state):
        if on_state:
            self.power_on(host)
        else:
            self.power_off(host)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='remote power control')
    parser.add_argument('--host', type=str, default=None,
                        help='name of host in database')
    parser.add_argument('--on', action='store_true', default=False,
                        help='turn host on')
    parser.add_argument('--off', action='store_true', default=False,
                        help='turn host off')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='verbose debugging output')
    args = parser.parse_args()
    if not args.host or (args.on and args.off):
        parser.print_help()
        sys.exit(1)

    urpower = UrPower(args.debug)
    if args.on:
        urpower.set_state(args.host, True)
    elif args.off:
        urpower.set_state(args.host, False)
    else:
        urpower.status(args.host)
    del urpower


if __name__ == '__main__':
    main()
    sys.exit(0)
