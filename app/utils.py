from flask import jsonify


def ok(data=None, message="Success", code=200):
    return jsonify({"success": True, "message": message, "data": data}), code


def err(message="Error", code=400, data=None):
    return jsonify({"success": False, "message": message, "data": data}), code
