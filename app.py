from flask import Flask, render_template

import config
from core.database import init_db
from routes.characters import bp as characters_bp
from routes.chat import bp as chat_bp
from routes.models import bp as models_bp
from routes.personas import bp as personas_bp
from routes.assistant import bp as assistant_bp
from routes.images import bp as images_bp
from routes.project import bp as project_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_IMAGE_UPLOAD_MB * 1024 * 1024
    for d in (config.DATA_DIR, config.MODELS_DIR, config.IMAGE_MODELS_DIR, config.LORA_MODELS_DIR, config.GENERATED_IMAGES_DIR):
        import os; os.makedirs(d, exist_ok=True)

    init_db()

    app.register_blueprint(characters_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(personas_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(project_bp)

    @app.get("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
