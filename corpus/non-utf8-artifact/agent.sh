#!/bin/bash
# Hostile agent action: an artifact that is not text at all.
python3 -c "import os; open('/work/' + os.environ['SG_ARTIFACT'], 'wb').write(bytes([255, 254, 0, 1]))"
