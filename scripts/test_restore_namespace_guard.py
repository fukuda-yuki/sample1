from pathlib import Path
import unittest
from unittest.mock import patch
from check_preservation_restore import drill
from check_restore_namespace import main


class NamespaceTests(unittest.TestCase):
    def test_full_drill_rejects_host_namespace_before_docker_or_files(self):
        for env in ({}, {'SAMPLE1_HOST_NETWORK_NAMESPACE':'net:host'}):
            with patch.dict('os.environ',env,clear=True),patch('os.readlink',return_value='net:host'),patch('subprocess.check_output') as docker:
                with self.assertRaises(ValueError):drill(Path('unused'),{},Path('unused'))
                docker.assert_not_called()

    def test_daemon_diagnostic_rejects_host_namespace(self):
        with patch('os.readlink',return_value='net:host'),patch('subprocess.run') as mutation:
            with self.assertRaises(ValueError):main(Path('unused'))
            mutation.assert_not_called()
