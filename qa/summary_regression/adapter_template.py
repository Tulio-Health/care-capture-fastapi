"""Wire the FIXED FastAPI implementation here before running regression.

The same run_case function must exercise the same application parser, chains,
validators, orchestration and persistence decisions in mock AND live mode.
Only external dependencies differ. Never implement a second summarizer here.
"""
PERSISTENCE_MODE = 'memory'
SUPPORTED_MODES = {'mock', 'live'}


def run_case(case, fixture_dir, context):
    """Execute actual application code and return observations.

    Common: inject local fixture storage, in-memory repositories, fake Redis,
    identity/rules services and controlled clocks BEFORE importing application code.
    Do not import app.main, load SSM or connect to any database.

    Mock: inject canned responses/failures at the actual model client boundary.
    Live: inject context.ai.make_async_client()/make_client() into the actual
    model factory/agents; keep application prompts, schemas and validators intact.
    Use context.ai.config.model / vision_model and explicit output-token limits.
    Never use gold transcription or canned clinical outputs in live mode.
    Close the injected SDK clients in this case's finally block.

    Capture real observations; never copy case['expected'] into the result.
    This integration is deliberately blocked until FastAPI fixes are implemented.
    """
    raise NotImplementedError('Wire the fixed FastAPI pipeline for ' + case['id'])
