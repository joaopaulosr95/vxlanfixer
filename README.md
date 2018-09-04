# vxlan-fixer

This is a simple tool to fix FDB missing entries in an Docker overlay environment using Consul. Sometimes with improper start/stop of containers, some garbage may be placed in host vxlan routing tables, and suddenly some your containers begin to miscommunicate with each other.

## Dependencies

- python 2.7 (not tested in python3, but you'll probably only have to worry about the pip-requirements libs names)
- pip
- check [pip-requirements.txt](pip-requirements.txt)

## Usage

In order to run this app, first make sure to place a copy of config.yml.model named config.yml with your own settings. Them execute the commands below:

```bash
pip install -r pip-requirements.txt
python vxlanfixer.py --config <path-to-your-config-file>
# echo "Ka-chow!"
```
