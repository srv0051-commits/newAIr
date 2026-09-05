from flask import Flask, render_template

import config
from core.database import init_db
from routes.characters import bp as characters_bp
from routes.chat import bp as chat_bp
from routes.models import bp as models_bp
from routes.personas import bp as personas_bp
from routes.assistant import bp as assistant_bp
from routes.images import bp as images_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    init_db()

    app.register_blueprint(characters_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(personas_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(images_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
