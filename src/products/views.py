from django.core.exceptions import ImproperlyConfigured
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone




from rest_framework import filters
from rest_framework import generics
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.reverse import reverse as api_reverse
from rest_framework.views import APIView

# Create your views here.
from .filters import ProductFilter
from .forms import VariationInventoryFormSet, ProductFilterForm
from .mixins import StaffRequiredMixin
from .models import Product, Variation, Category
from .pagination import ProductPagination, CategoryPagination
from .serializers import (
		CategorySerializer, 
		ProductSerializer,
		 ProductDetailSerializer, 
		 ProductDetailUpdateSerializer
		)





# API CBVS


class APIHomeView(APIView):
	# authentication_classes = [SessionAuthentication]
	# permission_classes = [IsAuthenticated]
	def get(self, request, format=None):
		data = {
			"auth": {
				"login_url":  api_reverse("auth_login_api", request=request),
				"refresh_url":  api_reverse("refresh_token_api", request=request), 
				"user_checkout":  api_reverse("user_checkout_api", request=request), 
			},
			"address": {
				"url": api_reverse("user_address_list_api", request=request),
				"create":   api_reverse("user_address_create_api", request=request),
			},
			"checkout": {
				"cart": api_reverse("cart_api", request=request),
				"checkout": api_reverse("checkout_api", request=request),
				"finalize": api_reverse("checkout_finalize_api", request=request),
			},
			"products": {
				"count": Product.objects.all().count(),
				"url": api_reverse("products_api", request=request)
			},
			"categories": {
				"count": Category.objects.all().count(),
				"url": api_reverse("categories_api", request=request)
			},
			"orders": {
				"url": api_reverse("orders_api", request=request),
			}
		}
		return Response(data)




class CategoryListAPIView(generics.ListAPIView):
	queryset = Category.objects.all()
	serializer_class = CategorySerializer
	pagination_class = CategoryPagination


class CategoryRetrieveAPIView(generics.RetrieveAPIView):
	#authentication_classes = [SessionAuthentication]
	#permission_classes = [IsAuthenticated]
	queryset = Category.objects.all()
	serializer_class = CategorySerializer


class ProductListAPIView(generics.ListAPIView):
	#permission_classes = [IsAuthenticated]
	queryset = Product.objects.all()
	serializer_class = ProductSerializer
	filter_backends = [
					filters.SearchFilter, 
					filters.OrderingFilter, 
					filters.DjangoFilterBackend
					]
	search_fields = ["title", "description"]
	ordering_fields  = ["title", "id"]
	filter_class = ProductFilter
	#pagination_class = ProductPagination


class ProductRetrieveAPIView(generics.RetrieveAPIView):
	queryset = Product.objects.all()
	serializer_class = ProductDetailSerializer


class ProductCreateAPIView(generics.CreateAPIView):
	queryset = Product.objects.all()
	serializer_class = ProductDetailUpdateSerializer



# CBVs

class CategoryListView(ListView):
	model = Category
	queryset = Category.objects.all()
	template_name = "products/product_list.html"


class CategoryDetailView(DetailView):
	model = Category

	def get_context_data(self, *args, **kwargs):
		context = super(CategoryDetailView, self).get_context_data(*args, **kwargs)
		obj = self.get_object()
		product_set = obj.product_set.all()
		default_products = obj.default_category.all()
		products = ( product_set | default_products ).distinct()
		context["products"] = products
		return context



class VariationListView(StaffRequiredMixin, ListView):
	model = Variation
	queryset = Variation.objects.all()

	def get_context_data(self, *args, **kwargs):
		context = super(VariationListView, self).get_context_data(*args, **kwargs)
		context["formset"] = VariationInventoryFormSet(queryset=self.get_queryset())
		return context

	def get_queryset(self, *args, **kwargs):
		product_pk = self.kwargs.get("pk")
		if product_pk:
			product = get_object_or_404(Product, pk=product_pk)
			queryset = Variation.objects.filter(product=product)
		return queryset

	def post(self, request, *args, **kwargs):
		formset = VariationInventoryFormSet(request.POST, request.FILES)
		if formset.is_valid():
			formset.save(commit=False)
			for form in formset:
				new_item = form.save(commit=False)
				#if new_item.title:
				product_pk = self.kwargs.get("pk")
				product = get_object_or_404(Product, pk=product_pk)
				new_item.product = product
				new_item.save()
				
			messages.success(request, "Your inventory and pricing has been updated.")
			return redirect("products")
		raise Http404






def product_list(request):
	qs = Product.objects.all()
	ordering = request.GET.get("ordering")
	if ordering:
		qs = Product.objects.all().order_by(ordering)
	f = ProductFilter(request.GET, queryset=qs)
	return render(request, "products/product_list.html", {"object_list": f })


class FilterMixin(object):
	filter_class = None
	search_ordering_param = "ordering"

	def get_queryset(self, *args, **kwargs):
		try:
			qs = super(FilterMixin, self).get_queryset(*args, **kwargs)
			return qs
		except:
			raise ImproperlyConfigured("You must have a queryset in order to use the FilterMixin")

	def get_context_data(self, *args, **kwargs):
		context = super(FilterMixin, self).get_context_data(*args, **kwargs)
		qs = self.get_queryset()
		ordering = self.request.GET.get(self.search_ordering_param)
		if ordering:
			qs = qs.order_by(ordering)
		filter_class = self.filter_class
		if filter_class:
			f = filter_class(self.request.GET, queryset=qs)
			context["object_list"] = f
		return context




class ProductListView(FilterMixin, ListView):
	model = Product
	queryset = Product.objects.all()
	filter_class = ProductFilter


	def get_context_data(self, *args, **kwargs):
		context = super(ProductListView, self).get_context_data(*args, **kwargs)
		context["now"] = timezone.now()
		context["query"] = self.request.GET.get("q") #None
		context["filter_form"] = ProductFilterForm(data=self.request.GET or None)
		return context

	def get_queryset(self, *args, **kwargs):
		qs = super(ProductListView, self).get_queryset(*args, **kwargs)
		query = self.request.GET.get("q")
		if query:
			qs = self.model.objects.filter(
				Q(title__icontains=query) |
				Q(description__icontains=query)
				)
			try:
				qs2 = self.model.objects.filter(
					Q(price=query)
				)
				qs = (qs | qs2).distinct()
			except:
				pass
		return qs


import random
class ProductDetailView(DetailView):
	model = Product
	#template_name = "product.html"
	#template_name = "<appname>/<modelname>_detail.html"
	def get_context_data(self, *args, **kwargs):
		context = super(ProductDetailView, self).get_context_data(*args, **kwargs)
		instance = self.get_object()
		#order_by("-title")
		context["related"] = sorted(Product.objects.get_related(instance)[:6], key= lambda x: random.random())
		return context





def product_detail_view_func(request, id):
	#product_instance = Product.objects.get(id=id)
	product_instance = get_object_or_404(Product, id=id)
	try:
		product_instance = Product.objects.get(id=id)
	except Product.DoesNotExist:
		raise Http404
	except:
		raise Http404

	template = "products/product_detail.html"
	context = {	
		"object": product_instance
	}
	return render(request, template, context)