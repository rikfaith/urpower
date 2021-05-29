# urpower

## Introduction

urpower is used to control the power of computers connected to either of:

* CPS Power Distributed Unit (tested with CyberPower PDU15SW8FNET)
* APC Switched Rack PDU (tested with APC AP7900)


SNMP needs to be enabled on the PDUs, with community names "public" for read
and "private" for write.

If a computer is turned on via the PDU, then the IPMI will also be powered on.

## Configuration File

The INI-format configuration file is stored in ~/.urpower

This file contains one entry per system. If a system does not have IPMI, but
is attached to the PDU, an entry looks like this:

> [home2]
> pdu = pdu-wb
> outlet = 6

Where, in the above example, "pdu-wb" is the hostname for the PDU, and "6" is
the outlet number on that PDU.

If the system has IPMI as well as a PDU, an entry looks looks like this:

> [morpheus]
> pdu = pdu-wt
> outlet = 4
> ipmi_host = morpheus-i
> ipmi_username = admin
> ipmi_password = admin

The additional fields specify the hostname for IPMI as well as the username
and password of the IPMI interface.

## Future enhancements

In the future, it should be possible to:
* power cycle a system, using IPMI (if available)
* power off a system using IPMI while leaving the PDU outlet on
