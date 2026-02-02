# ==========================================
# SHINQIT MARKET - ALL-IN-ONE BACKEND CORE
# ==========================================

from django.db import models
from django.contrib.auth.models import AbstractUser
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.decorators import api_view
import openai
import stripe

# 1. القواعد البيانية (Models)
# ---------------------------

class User(AbstractUser):
    is_seller = models.BooleanField(default=False)
    phone = models.CharField(max_length=15, blank=True)
    fcm_token = models.CharField(max_length=255, blank=True) # للإشعارات

class Shop(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

class Product(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='products')
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', null=True)

class Order(models.Model):
    buyer = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='PENDING') # PENDING, PAID, SHIPPED

class LocalPayment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    transaction_number = models.CharField(max_length=100, unique=True)
    is_verified = models.BooleanField(default=False)

# 2. تحويل البيانات (Serializers)
# -------------------------------

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

# 3. محرك الذكاء الاصطناعي (AI Logic)
# ----------------------------------

def ai_generate_description(product_name):
    client = openai.OpenAI(api_key="YOUR_KEY")
    prompt = f"اكتب وصفاً تسويقياً لمنتج: {product_name} لسوق موريتانيا."
    response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content

# 4. واجهات البرمجة (API Views)
# ------------------------------

# --- للمشتري: البحث والعرض ---
@api_view(['GET'])
def list_products(request):
    query = request.query_params.get('search', '')
    products = Product.objects.filter(models.Q(title__icontains=query))
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)

# --- للبائع: إضافة منتج بالذكاء الاصطناعي ---
@api_view(['POST'])
def add_product_ai(request):
    name = request.data.get('title')
    ai_desc = ai_generate_description(name) # توليد الوصف آلياً
    data = request.data.copy()
    data['description'] = ai_desc
    serializer = ProductSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

# --- نظام الدفع الهجين (Stripe & Bankily) ---
@api_view(['POST'])
def process_payment(request):
    method = request.data.get('method') # 'STRIPE' or 'BANKILY'
    order_id = request.data.get('order_id')
    order = Order.objects.get(id=order_id)

    if method == 'STRIPE':
        # دفع دولي
        intent = stripe.PaymentIntent.create(amount=1000, currency='usd')
        return Response({'client_secret': intent.client_secret})
    
    elif method == 'BANKILY':
        # دفع محلي (انتظار تأكيد المشرف)
        LocalPayment.objects.create(order=order, transaction_number=request.data.get('tx_id'))
        order.status = 'AWAITING_CONFIRMATION'
        order.save()
        return Response({"message": "تم استلام طلب الدفع المحلي"})

# --- المشرف: تأكيد العمولة والعملية ---
@api_view(['POST'])
def admin_approve_payment(request, payment_id):
    payment = LocalPayment.objects.get(id=payment_id)
    payment.is_verified = True
    payment.save()
    
    order = payment.order
    order.status = 'PAID'
    order.save()
    
    # حساب العمولة (5%)
    commission = order.total_price * 0.05
    return Response({"message": f"تم التأكيد، عمولة المنصة: {commission}"})
