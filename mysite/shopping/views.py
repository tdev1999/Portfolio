"""views.py"""
import os
import io
import csv
import json
from pathlib import Path
from django.conf import settings
from django.shortcuts import redirect, render
from django.http.response import JsonResponse
from django.views import generic
from django.views.generic import FormView
from django.urls import reverse_lazy
import stripe
from .models import Products, BuyingHistory
from .forms import ProductForm, UploadCSVForm, EditForm

# read APIKEY
with open(settings.BASE_DIR + '/shopping/api_setting/apikey.txt', mode='r') as file:
    stripe.api_key = file.read()

class UploadSingleView(FormView):
    """UploadSingleView"""
    form_class = ProductForm
    success_url = reverse_lazy('shp:index')

    def form_valid(self, form):
        # prepare
        code = form.cleaned_data.get('code')
        orgname, ext = os.path.splitext(form.cleaned_data["picture"].name)
        upload_dir = '/shopping/static/shopping/img/'
        # make dir if not exists the dir
        Path(settings.BASE_DIR + upload_dir).mkdir(parents=True, exist_ok=True)
        # delete if record is exists as same.
        newfilepath = settings.BASE_DIR + upload_dir + code + ext
        if os.path.exists(newfilepath):
            os.remove(newfilepath)
            Products.objects.filter(code=code).delete()
        # save and rename
        form.save()
        orgfilepath = settings.BASE_DIR + upload_dir + orgname + ext
        os.rename(orgfilepath, newfilepath)
        return super().form_valid(form)

class UploadBulkView(FormView):
    """UploadBulkView"""
    form_class = UploadCSVForm
    success_url = reverse_lazy('shp:index')

    def form_valid(self, form):
        # prepare
        csvfile = io.TextIOWrapper(form.cleaned_data["file"], encoding='utf-8')
        # read csv and ignore header
        reader = csv.reader(csvfile)
        next(reader)
        # upsert
        for record in reader:
            product, created = Products.objects.get_or_create(code=record[0])
            if not created:
                product.code = record[0]
                product.name = record[1]
                product.price = record[2]
                product.description = record[3]
                product.save()
        return super().form_valid(form)

class IndexView(generic.TemplateView):
    """IndexView"""
    template_name = 'shopping/index.html'
    # model = Products
    # paginate_by = 5 # TODO paging

    def post(self, request, *args, **kwargs):
        """post"""
        # mode read
        mode = self.kwargs.get("mode")
        if mode != 0:
            # update
            form = EditForm(request.POST)
            if form.is_valid():
                product = Products.objects.get(code=form.cleaned_data['code'])
                product.code = form.cleaned_data['code']
                product.name = form.cleaned_data['name']
                product.price = form.cleaned_data['price']
                product.description = form.cleaned_data['description']
                product.save()
            return redirect('shp:index')
        # read
        data = json.loads(request.body)
        data = Products.objects.get(code=data.get('code'))
        # responce json
        return JsonResponse({
            "code": data.code,
            "name": data.name,
            "price": data.price,
            "description": data.description
        })

    def get_context_data(self, **kwargs):
        # prepare blank form
        context = super().get_context_data(**kwargs)
        context['products'] = Products.objects.all()
        context['form_single'] = ProductForm()
        context['form_csv'] = UploadCSVForm()
        context['editablelist'] = Products.objects.order_by('id')[:5]
        context['editableform'] = EditForm()
        return context

class DetailView(generic.DetailView):
    """DetailView"""
    template_name = 'shopping/detail.html'
    model = Products

    def post(self, request, *args, **kwargs):
        """post"""
        product = self.get_object()
        token = request.POST['stripeToken']  # 'stripeToken' will made by form submit
        try:
            # buy
            charge = stripe.Charge.create(
                amount=product.price,
                currency='jpy',
                source=token,
                description='メール:{} 商品名:{}'.format(request.user.email, product.name),
            )
        except stripe.error.CardError as errors:
            # errors: Payment was not successful. e.g. payment limit over
            context = self.get_context_data()
            context['message'] = errors.error.message
            return render(request, 'shopping/product_detail.html', context)
        else:
            # ok
            BuyingHistory.objects.create(product=product, user=request.user, stripe_id=charge.id)
            return redirect('shp:index')

    def get_context_data(self, **kwargs):
        """STRIPE_PUBLIC_KEYを渡したいだけ"""
        context = super().get_context_data(**kwargs)
        context['public_key'] = settings.STRIPE_PUBLIC_KEY
        return context
