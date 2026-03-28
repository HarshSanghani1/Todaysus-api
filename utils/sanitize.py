"""Utility to sanitize MongoDB documents for JSON response."""
from datetime import datetime
from bson import ObjectId


def sanitize_doc(doc):
    """Convert a MongoDB document to a JSON-safe dict.
    - ObjectId → str
    - datetime → ISO string
    - Recursively handles nested dicts and lists
    """
    if doc is None:
        return None
    if isinstance(doc, list):
        return [sanitize_doc(item) for item in doc]
    if not isinstance(doc, dict):
        return doc

    result = {}
    for key, val in doc.items():
        if isinstance(val, ObjectId):
            result[key] = str(val)
        elif isinstance(val, datetime):
            result[key] = val.isoformat() + "Z"
        elif isinstance(val, dict):
            # Handle PyMongo $date format
            if "$date" in val:
                result[key] = val["$date"] if isinstance(val["$date"], str) else str(val["$date"])
            else:
                result[key] = sanitize_doc(val)
        elif isinstance(val, list):
            result[key] = sanitize_doc(val)
        else:
            result[key] = val
    return result


def sanitize_docs(docs):
    """Convert a list of MongoDB documents."""
    return [sanitize_doc(d) for d in docs]
