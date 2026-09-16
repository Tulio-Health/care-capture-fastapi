"""Construct the real application with no secrets, startup tasks or network access."""
import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
from run_pack import no_network

class FactorySafety(unittest.TestCase):
    def test_real_routes_construct_without_external_connections(self):
        with no_network(), patch.dict(os.environ, {'LANGSMITH_TRACING':'false','LANGCHAIN_TRACING_V2':'false'},clear=True):
            from src.app.core.settings import Settings
            settings=Settings(_env_file=None,OPENAI_API_KEY='sk-qa-unusable',DB_HOST='qa.invalid',DB_USER='qa',DB_PASSWORD='unused')
            with patch('src.app.core.settings.get_settings',return_value=settings),patch('src.app.core.get_settings',return_value=settings):
                from src.app.application import get_application
                @asynccontextmanager
                async def lifespan(app):yield
                app=get_application(initialize_environment=False,lifespan_handler=lifespan)
                paths={route.path for route in app.routes}
                self.assertTrue(any('summar' in path for path in paths))
                self.assertTrue(any('health' in path for path in paths))

if __name__=='__main__':unittest.main()
