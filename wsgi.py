from server import app, validate_app_config

validate_app_config(require_secret=True)

application = app
