#!/bin/bash
# Hostile agent action: an artifact far larger than any real solution (3 MB).
python3 -c "import os; open('/work/' + os.environ['SG_ARTIFACT'], 'w').write('a' * 3000000)"
