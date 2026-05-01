import http.server
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

class FakePayHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        print("------INBOUND REQUEST----")
        if self.path == '/fakepay':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                print(f"INPUT: {data} : type:{type(data)}")
                if not isinstance(data, dict):
                    message = "Incorrect body format supplied, I need to extract dict from json"
                else:
                    message = self.validate_card(data)
                print(f"CARD VALIDATION: {message}")
                if message == "VALID":
                    response = {'message': 'Payment processed successfully'}
                    self.send_response(200)
                else:
                    response = {'error': 'payment failed', 'reason': message}
                    self.send_response(400)
            except json.JSONDecodeError as error:
                response = {'error': 'Invalid JSON payload', 'reason': str(error)}
                self.send_response(400)
            
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
        print("------------DONE----------")

    def validate_card(self, data):
        if 'transactionId' not in data:
            return "Missing transactionId"
        if 'card' not in data:
            return "Missing Card Object"
        
        card = data.get('card', None)
            
        # Regex for PAN (16-digit number)
        pan_regex = r'^[0-9]{16}$'
        # Regex for expiry (MM-YYYY format)
        expiry_regex = r'^(0[1-9]|1[0-2])-\d{4}$'
        # Regex for name (only letters and spaces)
        name_regex = r'^[A-Za-z\s]+$'
        uuid_regex = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

        if not re.match(uuid_regex, str(data.get('transactionId', None))):
            return "Invalid transactionId. It must match UUID"
        # Validate PAN
        if not re.match(pan_regex, str(card.get('number', None))):
            return "Invalid card pan. It must be a 16-digit number."

        # Validate expiry
        if not re.match(expiry_regex, str(card.get('expiry', None))):
            return "Invalid card expiry. It must be in MM-YYYY format."

        # Validate name
        if not re.match(name_regex, card.get('name', None)):
            return "Invalid card name. It must contain only letters and spaces."

        return "VALID"

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 9000), FakePayHandler)
    print("Server running on http://127.0.0.1:9000")
    server.serve_forever()
