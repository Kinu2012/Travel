from flask import Flask

def create_app():
    app = Flask(name)
    app.config.from_prefixed_env()  # .envを読み込む

    from apps import routes
    app.register_blueprint(routes.bp)

    return app
