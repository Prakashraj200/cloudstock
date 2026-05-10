from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# MongoDB Connection - Updated with your Atlas connection string
MONGO_URI = "mongodb+srv://prakashrajmca_db_user:jKVqzxEB79CHkOJT@cluster0.pyulwal.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['inventory_management']

# Collections
products_collection = db['products']
notifications_collection = db['notifications']
reorders_collection = db['reorders']
users_collection = db['users']
product_requests_collection = db['product_requests']
sales_collection = db['sales']

# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'owner':
            return jsonify({'error': 'Owner access required', 'redirect': '/login'}), 403
        return f(*args, **kwargs)
    return decorated_function

def supplier_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_type') != 'supplier':
            return jsonify({'error': 'Supplier access required', 'redirect': '/login'}), 403
        return f(*args, **kwargs)
    return decorated_function

# Page routes
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('user_type') == 'owner':
            return redirect(url_for('owner_dashboard'))
        elif session.get('user_type') == 'supplier':
            return redirect(url_for('supplier_dashboard'))
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/owner-dashboard')
def owner_dashboard():
    if 'user_id' not in session or session.get('user_type') != 'owner':
        return redirect(url_for('login'))
    return render_template('owner_dashboard.html')

@app.route('/supplier-dashboard')
def supplier_dashboard():
    if 'user_id' not in session or session.get('user_type') != 'supplier':
        return redirect(url_for('login'))
    return render_template('supplier_dashboard.html')

# Authentication APIs
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    
    existing_user = users_collection.find_one({'email': data['email']})
    if existing_user:
        return jsonify({'error': 'Email already registered'}), 400
    
    user = {
        'name': data['name'],
        'email': data['email'],
        'password': generate_password_hash(data['password']),
        'user_type': data['user_type'],
        'company_name': data.get('company_name', ''),
        'phone': data.get('phone', ''),
        'created_at': datetime.now()
    }
    
    result = users_collection.insert_one(user)
    return jsonify({'message': 'Registration successful', 'user_id': str(result.inserted_id)}), 201

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = users_collection.find_one({'email': data['email']})
    
    if not user or not check_password_hash(user['password'], data['password']):
        return jsonify({'error': 'Invalid email or password'}), 401
    
    session['user_id'] = str(user['_id'])
    session['user_name'] = user['name']
    session['user_type'] = user['user_type']
    session['user_email'] = user['email']
    session['company_name'] = user.get('company_name', '')
    
    return jsonify({
        'message': 'Login successful',
        'user_type': user['user_type'],
        'user_name': user['name']
    })

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})

@app.route('/api/current-user', methods=['GET'])
@login_required
def get_current_user():
    return jsonify({
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'user_type': session.get('user_type'),
        'user_email': session.get('user_email'),
        'company_name': session.get('company_name')
    })

# Get list of owners for suppliers
@app.route('/api/owners', methods=['GET'])
@supplier_required
def get_owners():
    owners = list(users_collection.find(
        {'user_type': 'owner'},
        {'name': 1, 'email': 1, 'company_name': 1}
    ))
    for owner in owners:
        owner['_id'] = str(owner['_id'])
    return jsonify(owners)

# Product Request APIs
@app.route('/api/product-requests', methods=['POST'])
@supplier_required
def create_product_request():
    data = request.json
    
    if 'owner_email' not in data:
        return jsonify({'error': 'Owner email is required'}), 400
    
    owner = users_collection.find_one({'email': data['owner_email'], 'user_type': 'owner'})
    if not owner:
        return jsonify({'error': 'Owner not found'}), 404
    
    product_request = {
        'name': data['name'],
        'current_stock': int(data['current_stock']),
        'min_stock_level': int(data['min_stock_level']),
        'price': float(data['price']),
        'supplier_id': session.get('user_id'),
        'supplier_name': session.get('user_name'),
        'supplier_email': session.get('user_email'),
        'owner_id': str(owner['_id']),
        'owner_email': owner['email'],
        'owner_name': owner['name'],
        'status': 'pending',
        'created_at': datetime.now()
    }
    
    result = product_requests_collection.insert_one(product_request)
    
    # Notify owner via WebSocket
    socketio.emit('new_product_request', {
        'request_id': str(result.inserted_id),
        'product_name': data['name'],
        'supplier_name': session.get('user_name')
    }, room=owner['email'])
    
    return jsonify({'message': 'Request submitted successfully', '_id': str(result.inserted_id)}), 201

@app.route('/api/product-requests', methods=['GET'])
@login_required
def get_product_requests():
    if session.get('user_type') == 'owner':
        requests = list(product_requests_collection.find({
            'owner_id': session.get('user_id')
        }).sort('created_at', -1))
    else:
        requests = list(product_requests_collection.find({
            'supplier_email': session.get('user_email')
        }).sort('created_at', -1))
    
    for req in requests:
        req['_id'] = str(req['_id'])
        req['created_at'] = req['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(requests)

@app.route('/api/product-requests/<request_id>/approve', methods=['POST'])
@owner_required
def approve_product_request(request_id):
    product_request = product_requests_collection.find_one({'_id': ObjectId(request_id)})
    
    if not product_request:
        return jsonify({'error': 'Request not found'}), 404
    
    if product_request['owner_id'] != session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Create product
    product = {
        'name': product_request['name'],
        'current_stock': product_request['current_stock'],
        'min_stock_level': product_request['min_stock_level'],
        'price': product_request['price'],
        'supplier_id': product_request['supplier_id'],
        'supplier_name': product_request['supplier_name'],
        'supplier_email': product_request['supplier_email'],
        'owner_id': session.get('user_id'),
        'owner_email': session.get('user_email'),
        'owner_name': session.get('user_name'),
        'created_at': datetime.now()
    }
    products_collection.insert_one(product)
    
    # Update request status
    product_requests_collection.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {'status': 'approved', 'approved_at': datetime.now()}}
    )
    
    # Notify supplier
    socketio.emit('product_request_approved', {
        'product_name': product_request['name'],
        'owner_name': session.get('user_name')
    }, room=product_request['supplier_email'])
    
    return jsonify({'message': 'Product approved and added to inventory'})

@app.route('/api/product-requests/<request_id>/reject', methods=['POST'])
@owner_required
def reject_product_request(request_id):
    product_request = product_requests_collection.find_one({'_id': ObjectId(request_id)})
    
    if not product_request:
        return jsonify({'error': 'Request not found'}), 404
    
    if product_request['owner_id'] != session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    product_requests_collection.update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {'status': 'rejected', 'rejected_at': datetime.now()}}
    )
    
    # Notify supplier
    socketio.emit('product_request_rejected', {
        'product_name': product_request['name'],
        'owner_name': session.get('user_name')
    }, room=product_request['supplier_email'])
    
    return jsonify({'message': 'Product request rejected'})

# Product APIs
@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    if session.get('user_type') == 'supplier':
        products = list(products_collection.find({'supplier_email': session.get('user_email')}))
    elif session.get('user_type') == 'owner':
        products = list(products_collection.find({'owner_id': session.get('user_id')}))
    else:
        products = []
    
    for product in products:
        product['_id'] = str(product['_id'])
    return jsonify(products)

# Sale/Purchase API - Owner sells products to customers
@app.route('/api/products/<product_id>/sell', methods=['POST'])
@owner_required
def sell_product(product_id):
    data = request.json
    quantity = int(data['quantity'])
    
    product = products_collection.find_one({'_id': ObjectId(product_id)})
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if product['owner_id'] != session.get('user_id'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    new_stock = product['current_stock'] - quantity
    
    if new_stock < 0:
        return jsonify({'error': 'Insufficient stock'}), 400
    
    # Update stock
    products_collection.update_one(
        {'_id': ObjectId(product_id)},
        {'$set': {'current_stock': new_stock, 'last_updated': datetime.now()}}
    )
    
    # Record sale
    sale = {
        'product_id': product_id,
        'product_name': product['name'],
        'quantity': quantity,
        'price': product['price'],
        'total_amount': quantity * product['price'],
        'owner_id': session.get('user_id'),
        'owner_email': session.get('user_email'),
        'sale_date': datetime.now()
    }
    sales_collection.insert_one(sale)
    
    # Check if stock is NOW low (this is the key fix!)
    is_low_stock = new_stock <= product['min_stock_level']
    
    if is_low_stock:
        # Create notification for owner
        notification = {
            'product_id': product_id,
            'product_name': product['name'],
            'current_stock': new_stock,
            'min_stock_level': product['min_stock_level'],
            'supplier_email': product['supplier_email'],
            'supplier_name': product['supplier_name'],
            'owner_id': session.get('user_id'),
            'owner_email': session.get('user_email'),
            'message': f"⚠️ Low stock alert! {product['name']} - Current: {new_stock}, Minimum: {product['min_stock_level']}",
            'type': 'low_stock',
            'status': 'unread',
            'created_at': datetime.now()
        }
        notifications_collection.insert_one(notification)
        
        # Create auto-reorder for supplier
        reorder_quantity = max((product['min_stock_level'] * 2) - new_stock, product['min_stock_level'])
        reorder = {
            'product_id': product_id,
            'product_name': product['name'],
            'quantity': reorder_quantity,
            'supplier_id': product['supplier_id'],
            'supplier_name': product['supplier_name'],
            'supplier_email': product['supplier_email'],
            'owner_id': session.get('user_id'),
            'owner_email': session.get('user_email'),
            'owner_name': session.get('user_name'),
            'status': 'pending',
            'created_at': datetime.now()
        }
        reorder_result = reorders_collection.insert_one(reorder)
        
        # Notify owner via WebSocket
        socketio.emit('low_stock_alert', {
            'product_name': product['name'],
            'current_stock': new_stock,
            'min_stock_level': product['min_stock_level'],
            'supplier_name': product['supplier_name']
        }, room=session.get('user_email'))
        
        # Notify supplier via WebSocket
        socketio.emit('new_reorder', {
            'reorder_id': str(reorder_result.inserted_id),
            'product_name': product['name'],
            'quantity': reorder_quantity,
            'owner_name': session.get('user_name')
        }, room=product['supplier_email'])
    
    return jsonify({
        'message': 'Sale recorded successfully',
        'new_stock': new_stock,
        'low_stock': is_low_stock,
        'low_stock_details': {
            'product_name': product['name'],
            'current_stock': new_stock,
            'min_stock_level': product['min_stock_level']
        } if is_low_stock else None
    })

# Notifications API
@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    if session.get('user_type') == 'owner':
        notifications = list(notifications_collection.find({
            'owner_id': session.get('user_id')
        }).sort('created_at', -1))
    else:
        notifications = list(notifications_collection.find({
            'supplier_email': session.get('user_email')
        }).sort('created_at', -1))
    
    for notif in notifications:
        notif['_id'] = str(notif['_id'])
        notif['created_at'] = notif['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(notifications)

@app.route('/api/notifications/unread-count', methods=['GET'])
@login_required
def get_unread_count():
    if session.get('user_type') == 'owner':
        count = notifications_collection.count_documents({
            'owner_id': session.get('user_id'),
            'status': 'unread'
        })
    else:
        count = notifications_collection.count_documents({
            'supplier_email': session.get('user_email'),
            'status': 'unread'
        })
    return jsonify({'count': count})

@app.route('/api/notifications/<notification_id>/read', methods=['PUT'])
@login_required
def mark_notification_read(notification_id):
    notifications_collection.update_one(
        {'_id': ObjectId(notification_id)},
        {'$set': {'status': 'read'}}
    )
    return jsonify({'message': 'Marked as read'})

# Reorders API
@app.route('/api/reorders', methods=['GET'])
@login_required
def get_reorders():
    if session.get('user_type') == 'owner':
        reorders = list(reorders_collection.find({
            'owner_id': session.get('user_id')
        }).sort('created_at', -1))
    else:
        reorders = list(reorders_collection.find({
            'supplier_email': session.get('user_email')
        }).sort('created_at', -1))
    
    for reorder in reorders:
        reorder['_id'] = str(reorder['_id'])
        reorder['created_at'] = reorder['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(reorders)

@app.route('/api/reorders/<reorder_id>/status', methods=['PUT'])
@supplier_required
def update_reorder_status(reorder_id):
    data = request.json
    status = data['status']
    
    reorder = reorders_collection.find_one({'_id': ObjectId(reorder_id)})
    if not reorder:
        return jsonify({'error': 'Reorder not found'}), 404
    
    if reorder['supplier_email'] != session.get('user_email'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    reorders_collection.update_one(
        {'_id': ObjectId(reorder_id)},
        {'$set': {'status': status, 'updated_at': datetime.now()}}
    )
    
    # If delivered, update product stock
    if status == 'delivered':
        product = products_collection.find_one({'_id': ObjectId(reorder['product_id'])})
        if product:
            new_stock = product['current_stock'] + reorder['quantity']
            products_collection.update_one(
                {'_id': ObjectId(reorder['product_id'])},
                {'$set': {'current_stock': new_stock, 'last_updated': datetime.now()}}
            )
            
            # Notify owner
            socketio.emit('stock_updated', {
                'product_name': product['name'],
                'new_stock': new_stock,
                'supplier_name': reorder['supplier_name']
            }, room=reorder['owner_email'])
    
    return jsonify({'message': f'Reorder status updated to {status}'})

# Sales history
@app.route('/api/sales', methods=['GET'])
@owner_required
def get_sales():
    sales = list(sales_collection.find({
        'owner_id': session.get('user_id')
    }).sort('sale_date', -1).limit(50))
    
    for sale in sales:
        sale['_id'] = str(sale['_id'])
        sale['sale_date'] = sale['sale_date'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(sales)

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    if 'user_email' in session:
        join_room(session['user_email'])
        print(f"User {session['user_email']} joined room")
    emit('connection_response', {'data': 'Connected to server'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='127.0.0.1', port=5000)
    