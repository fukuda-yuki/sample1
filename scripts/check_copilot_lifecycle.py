"""Exercise shared container freeze/stop controls without a model or start grant."""
import argparse
from pathlib import Path
from unittest.mock import patch
from check_container_protocol import main
from run_codex import GATEWAY_IMAGE

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,required=True)
    a=p.parse_args()
    # The reused check has fixed Python-only commands and network=none.
    with patch('run_experiment.check_start',return_value={'kind':'synthetic-no-model'}), patch('run_experiment.reserve_start'):
        main(GATEWAY_IMAGE,a.evidence)
