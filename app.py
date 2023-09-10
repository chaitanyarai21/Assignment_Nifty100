from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
import flask_app


if __name__ == "__main__":
    # run_tests()
    app.run(port="8080")