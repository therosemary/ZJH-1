from django.contrib import admin
from BMS.notice_mixin import NotificationMixin
from BMS.admin_bms import BMS_admin_site
from .models import Bill, Invoice
from .models import Invoice as fm_Invoice
from datetime import datetime
from django.contrib import messages
from django.contrib.admin.views.main import ChangeList
from django.db.models import Sum
from django.forms.models import BaseInlineFormSet
from daterange_filter.filter import DateRangeFilter
from django.contrib.auth.models import User
from import_export import resources
from import_export.admin import ExportActionModelAdmin
from import_export import fields
from import_export.widgets import ForeignKeyWidget
from mm.models import Contract
from notification.signals import notify
from pm.models import SubProject
from django import forms
from BMS.settings import DINGTALK_APPKEY, DINGTALK_SECRET, DINGTALK_AGENT_ID
from em.models import Employees
from nm.models import DingtalkChat

class InvoiceForm(forms.ModelForm):
    '''
    财务开票的Form
    '''
    def clean_invoice_code(self):
        invoice_code = self.cleaned_data['invoice_code']
        for invoice in fm_Invoice.objects.all():
            if invoice.invoice_code == invoice_code and invoice.id != self.instance.id:
                raise forms.ValidationError('发票号码不能重复')
        return self.cleaned_data['invoice_code']


class InvoiceChangeList(ChangeList):
    '''
    财务开票ChangeList页面的统计
    '''
    def get_results(self, *args, **kwargs):
        super(InvoiceChangeList, self).get_results(*args, **kwargs)
        self.sum = []
        q_income = self.result_list.aggregate(income_sum=Sum('bill__income'))
        q_amount = self.result_list.aggregate(amount_sum=Sum('invoice__invoice__invoice__amount'))
        try:
            receivable_sum = (q_amount['amount_sum'] or 0) - (q_income['income_sum'] or 0)
            self.sum = [q_amount['amount_sum'],receivable_sum, q_income['income_sum']]
        except KeyError:
            self.sum = ['','', '']


class InvoiceInfoResource(resources.ModelResource):
    '''
    财务发票的导出
    '''
    contract_salesman = fields.Field(column_name='销售人员')
    invoice_contract_number = fields.Field(column_name='合同号',attribute='invoice__contract',widget=ForeignKeyWidget(Contract, 'contract_number'))
    contract_name = fields.Field(column_name='项目',attribute='invoice__contract',widget=ForeignKeyWidget(Contract, 'name'))
    invoice_title = fields.Field(column_name="发票抬头")
    contract_price = fields.Field(column_name='合同单价',attribute='invoice__contract',widget=ForeignKeyWidget(Contract, 'price'))
    contract_range = fields.Field(column_name='价格区间')
    contract_amount = fields.Field(column_name='合同金额')
    contract_income = fields.Field(column_name='回款金额',attribute='income')
    invoice_amount = fields.Field(column_name='发票金额')
    date = fields.Field(column_name='开票日期',attribute='date')
    contract_income_date = fields.Field(column_name='到款日期',attribute='income_date')
    invoice_code = fields.Field(column_name='发票号码',attribute='invoice_code')
    invoice_type = fields.Field(column_name='发票类型')
    invoice_tax_amount = fields.Field(column_name='开票税率',attribute='tax_amount')
    invoice_content = fields.Field(column_name='开票内容',attribute='invoice__content')
    invoice_issuingUnit = fields.Field(column_name='开票单位')

    class Meta:
        model = Invoice
        skip_unchanged = True
        fields = ('contract_salesman','invoice_contract_number','contract_name','invoice_title','contract_price','contract_range',
                  'contract_amount','invoice_amount','contract_income','date','contract_income_date','invoice_code',
                  'invoice_type','invoice_tax_amount','invoice_content','invoice_issuingUnit')
        export_order = ('contract_salesman','invoice_contract_number','contract_name','invoice_title','contract_price','contract_range',
                        'contract_amount','invoice_amount','contract_income','date','contract_income_date','invoice_code',
                        'invoice_type','invoice_tax_amount','invoice_content','invoice_issuingUnit')
    def dehydrate_contract_amount(self, invoice):
        return '%.2f' % (invoice.invoice.contract.fis_amount+invoice.invoice.contract.fin_amount)
    def dehydrate_contract_salesman(self,invoice):
        return '%s%s' % (invoice.invoice.contract.salesman.last_name,invoice.invoice.contract.salesman.first_name)
    def dehydrate_contract_range(self,invoice):
        return invoice.invoice.contract.get_range_display()
    def dehydrate_invoice_type(self,invoice):
        return invoice.invoice.get_type_display()
    def dehydrate_invoice_amount(self,invoice):
        return '%.2f' % (invoice.invoice.amount)
    def dehydrate_invoice_title(self,invoice):
        return invoice.invoice.title.title
    def dehydrate_invoice_issuingUnit(self,invoice):
        return invoice.invoice.get_issuingUnit_display()


class BillInlineFormSet(BaseInlineFormSet):
    '''财务发票的进账的FormSet（Inline）'''
    def clean(self):
        super(BillInlineFormSet, self).clean()
        total = 0
        for form in self.forms:
            if not form.is_valid():
                return
            # if form.cleaned_data and not form.cleaned_data['DELETE']:
            if form.cleaned_data:
                total += form.cleaned_data['income']
        self.instance.__total__ = total


class BillInline(admin.TabularInline):
    '''
    财务发票管理的进账（Inline）
    '''
    model = Bill
    formset = BillInlineFormSet
    extra = 1


class SaleListFilter(admin.SimpleListFilter):
    '''财务发票管理的过滤器'''
    title = '业务员'
    parameter_name = 'Sale'

    def lookups(self, request, model_admin):
        qs_sale = User.objects.filter(groups__id=3)
        qs_company = User.objects.filter(groups__id=6)
        value = ['sale'] + list(qs_sale.values_list('username', flat=True)) + \
                ['company'] + list(qs_company.values_list('username', flat=True))
        label = ['销售'] + ['——' + i.last_name + i.first_name for i in qs_sale] + \
                ['公司'] + ['——' + i.last_name + i.first_name for i in qs_company]
        return tuple(zip(value, label))

    def queryset(self, request, queryset):
        if self.value() == 'sale':
            return queryset.filter(invoice__contract__salesman__in=list(User.objects.filter(groups__id=3)))
        if self.value() == 'company':
            return queryset.filter(invoice__contract__salesman__in=list(User.objects.filter(groups__id=6)))
        qs = User.objects.filter(groups__in=[3, 6])
        for i in qs:
            if self.value() == i.username:
                return queryset.filter(invoice__contract__salesman=i)


class InvoiceAdmin(ExportActionModelAdmin, NotificationMixin):
    '''
    财务发票的Admin
    '''
    appkey = DINGTALK_APPKEY
    appsecret = DINGTALK_SECRET
    form = InvoiceForm
    resource_class = InvoiceInfoResource
    list_display = ('invoice_contract_number', 'invoice_contract_name', 'contract_amount', 'salesman_name',
                    'contract_type', 'invoice_period','invoice_issuingUnit', 'invoice_title', 'invoice_amount', 'income_date',
                    'bill_receivable', 'invoice_code', 'date', 'tracking_number', 'send_date','file_link')
    list_display_links = ('invoice_title', 'invoice_amount')
    search_fields = ('invoice__contract__contract_number','invoice__title__title','invoice_code','^invoice__amount','invoice__issuingUnit')

    def get_search_results(self, request, queryset, search_term):
        #TODO#先用固定数组，后期修改为调用invoice__issuingUnit的ISSUING_UNIT_CHOICES
        ISSUING_UNIT_CHOICES ={}
        ISSUING_UNIT_CHOICES['上海锐翌']='sh'
        ISSUING_UNIT_CHOICES['杭州拓宏']='hz'
        ISSUING_UNIT_CHOICES['山东锐翌']='sd'
        ISSUING_UNIT_CHOICES['金锐生物']='sz'
        if search_term in ISSUING_UNIT_CHOICES.keys():
            queryset, use_distinct = super().get_search_results(request, queryset, ISSUING_UNIT_CHOICES[search_term])
        else:
            queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset, use_distinct


    inlines = [
        BillInline,
    ]
    fieldsets = (
        ('申请信息', {
           'fields': (('invoice_issuingUnit','invoice_title','invoice_title_tariffItem', 'invoice_amount','invoice_type'),'invoice_content', 'invoice_note')
        }),
        ('开票信息', {
            'fields': ('invoice_code','tax_amount','date','invoice_file')
        }),
        ('邮寄信息', {
            'fields': ('tracking_number','send_date')
        })
    )
    def invoice_contract_number(self, obj):
        return obj.invoice.contract.contract_number
    invoice_contract_number.short_description = '合同号'

    def invoice_contract_name(self, obj):
        return obj.invoice.contract.name
    invoice_contract_name.short_description = '合同名'

    def contract_amount(self, obj):
        amount = obj.invoice.contract.fis_amount + obj.invoice.contract.fin_amount
        return amount
    contract_amount.short_description = '合同额'

    def salesman_name(self, obj):
        name = obj.invoice.contract.salesman.last_name + obj.invoice.contract.salesman.first_name
        if name:
            return name
        return obj.invoice.contract.salesman
    salesman_name.short_description = '业务员'

    def contract_type(self, obj):
        return obj.invoice.contract.get_type_display()
    contract_type.short_description = '类型'

    def invoice_period(self, obj):
        return obj.invoice.get_period_display()
    invoice_period.short_description = '款期'

    def invoice_issuingUnit(self,obj):
        return obj.invoice.get_issuingUnit_display()
    invoice_issuingUnit.short_description = '开票单位'

    def invoice_title(self, obj):
        return obj.invoice.title.title
    invoice_title.short_description = '发票抬头'

    def invoice_title_tariffItem(self,obj):
        return obj.invoice.title.tariffItem
    invoice_title_tariffItem.short_description = '发票税号'

    def invoice_amount(self, obj):
        return obj.invoice.amount
    invoice_amount.short_description = '发票金额'

    def invoice_type(self,obj):
        return obj.invoice.get_type_display()
    invoice_type.short_description = '发票类型'

    def invoice_content(self,obj):
        return obj.invoice.content
    invoice_content.short_description = '开票内容'

    def invoice_note(self, obj):
        return obj.invoice.note
    invoice_note.short_description = '备注'

    def bill_receivable(self, obj):
        """
        改进：是否可以接收来自于bill_income的计算值，避免重读查询
        :param obj:
        :return:
        """
        current_income_amounts = Bill.objects.filter(invoice__id=obj.id).values_list('income', flat=True)
        receivable = obj.invoice.invoice.invoice.amount - sum(current_income_amounts)
        return receivable
    bill_receivable.short_description = '应收金额'

    def save_model(self, request, obj, form, change):
        user_id = False
        if obj.invoice_code and not obj.date:
            obj.date = datetime.now()
        elif not obj.invoice_code:
            obj.date = None
        if obj.tracking_number and not obj.send_date:
            obj.send_date = datetime.now()
        elif not obj.tracking_number:
            obj.send_date = None
        obj.save()
        #开出发票后，通知相应销售人员。
        invoice = Invoice.objects.filter(id=obj.id)
        if change:
            if obj.invoice_code and obj.date:
                if (obj.invoice_code != invoice[0].invoice_code) and invoice:
                    content = "【上海锐翌生物科技有限公司-BMS系统测试通知】测试消息,修改发票，发票号码：%s 开票金额：%s" % (obj.invoice_code, obj.invoice.amount)
                    if Employees.objects.filter(user=obj.invoice.contract.salesman):
                        user_id = Employees.objects.get(user=obj.invoice.contract.salesman).dingtalk_id
                    if user_id:
                        self.send_work_notice(content, DINGTALK_AGENT_ID, user_id)
                    # 通知市场人员，内容：抬头，金额，
                    # TODO 需要添加创建合同的人员，这些的消息反馈给新建合同的人，暂时发给项目管理
                    self.send_group_message(content, DingtalkChat.objects.get(chat_name="项目管理钉钉群-BMS").chat_id)
        else:
            if obj.invoice_code and obj.date:
                content = "【上海锐翌生物科技有限公司-BMS系统测试通知】测试消息,开出发票，发票号码：%s 开票金额：%s"%(obj.invoice_code,obj.invoice.amount)
                if Employees.objects.filter(user=obj.invoice.contract.salesman):
                    user_id = Employees.objects.get(user=obj.invoice.contract.salesman).dingtalk_id
                if user_id:
                    self.send_work_notice(content, DINGTALK_AGENT_ID, user_id)
                # 通知市场人员，内容：抬头，金额，
                # TODO 需要添加创建合同的人员，这些的消息反馈给新建合同的人，暂时发给项目管理
                self.send_group_message(content, DingtalkChat.objects.get(chat_name="项目管理钉钉群-BMS").chat_id)
                # notify.send(request.user, recipient=obj.invoice.contract.salesman, verb='开出发票',description="发票号码：%s 开票金额：%s"%(obj.invoice_code,obj.invoice.amount))
            #通知市场人员，内容：抬头，金额，对应销售员。

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        if instances:
            sum_income = formset.instance.__total__
            invoice_amount = instances[0].invoice.invoice.amount
            obj_invoice = Invoice.objects.get(id=instances[-1].invoice.id)
            invoice_in_contract = Invoice.objects.filter(invoice__contract__id = instances[-1].invoice.invoice.contract.id)
            obj_contract = Contract.objects.get(id=instances[-1].invoice.invoice.contract.id)
            try:
                obj_project = SubProject.objects.get(contract__id=instances[-1].invoice.invoice.contract.id)
            except:
                obj_project = False
            if sum_income <= invoice_amount:
                for instance in instances:
                    instance.save()
                formset.save_m2m()
                obj_invoice.income = sum_income
                #最后一次到账的日期，更新到财务发票的到款日期
                obj_invoice.income_date = instances[-1].date
                obj_invoice.save()
                #更新合同的首尾款到款日期、到款总额、
                if instances[-1].invoice.invoice.period == "FIS":
                    obj_contract.fis_date = instances[-1].date
                    #如果首款有多张发票
                    invoice_in_contract = invoice_in_contract.filter(invoice__period="FIS")
                    if invoice_in_contract:
                        sum_income = sum([invoice_temp.income for invoice_temp in invoice_in_contract if invoice_temp.income])
                    obj_contract.fis_amount_in = sum_income
                    #合同的首款<bill金额的总和,在项目管理中的状态为待处理，尾款已到。
                    if obj_project:
                        if (sum_income >= obj_contract.fis_amount) and (obj_project.status < 2):
                            obj_project.status = 2
                if instances[-1].invoice.invoice.period == "FIN":
                    obj_contract.fin_date = instances[-1].date
                    # 如果尾款有多张发票
                    invoice_in_contract = invoice_in_contract.filter(invoice__period="FIN")
                    if invoice_in_contract:
                        sum_income = sum([invoice_temp.income for invoice_temp in invoice_in_contract if invoice_temp.income])
                    obj_contract.fin_amount_in = sum_income
                    if obj_project:
                        if sum_income >= obj_contract.fin_amount and (obj_project.status < 10):
                            obj_project.status = 3
                obj_contract.save()
                if obj_project:
                    obj_project.save()
                #新的到账 通知财务部5
                content = "【上海锐翌生物科技有限公司-BMS系统测试通知】测试消息,有一笔新到账，发票号：%s 到账金额：%s"%(obj_invoice,sum_income)
                # 新到账 通知相应的销售
                # if Employees.objects.filter(user=obj.invoice.contract.salesman):
                #     user_id = Employees.objects.get(user=obj.invoice.contract.salesman).dingtalk_id
                # if user_id:
                #     self.send_work_notice(content, DINGTALK_AGENT_ID, user_id)
                # TODO 需要添加创建合同的人员，这些的消息反馈给新建合同的人，暂时发给项目管理
                self.send_group_message(content, DingtalkChat.objects.get(chat_name="财务钉钉群-BMS").chat_id)
                # for j in User.objects.filter(groups__id=5):?
                #     notify.send(request.user, recipient=j, verb='填写一笔新到账',description="发票号：%s 到账金额：%s"%(obj_invoice,sum_income))
                # notify.send(request.user,recipient=obj_invoice.invoice.contract.salesman,verb='填写一笔新到账',description="发票号：%s 到账金额：%s"%(obj_invoice,sum_income))
            else:
                messages.set_level(request, messages.ERROR)
                self.message_user(request, '进账总额 %.2f 超过开票金额 %.2f' % (sum_income, invoice_amount),
                                  level=messages.ERROR)

    def get_changelist(self, request):
        return InvoiceChangeList

    def get_actions(self, request):
        # 无删除或新增权限人员取消actions,销售总监有export_admin_action权限
        actions = super().get_actions(request)
        ##TODO,测试的时候报错，需要修改
        # if not request.user.has_perm('fm.delete_invoice'):
        #     # actions = None
        #     del actions['delete_selected']
        if not request.user.has_perm('fm.add_invoice'):
            if not actions:
                actions = None
            elif 'delete_selected' in actions:
                del actions['delete_selected']
        return actions

    def get_readonly_fields(self, request, obj=None):
        # if not request.user.has_perm('fm.add_invoice'):
        #     return ['invoice_issuingUnit','invoice_title','invoice_title_tariffItem', 'invoice_amount','invoice_type','invoice_content', 'invoice_note', 'invoice_code', 'tracking_number','tax_amount','date','invoice_file']
        return ['invoice_issuingUnit','invoice_title','invoice_title_tariffItem', 'invoice_amount', 'invoice_type','invoice_content','invoice_note']

    def get_inline_instances(self, request, obj=None):
        #超级用户修改发票管理的时候,存在bill的内联table所有不添加了，
        if request.user.is_superuser:
            self.inlines = []
        else:
            self.inlines = [BillInline,]
        return super(InvoiceAdmin, self).get_inline_instances(request, obj)

    # def get_formsets_with_inlines(self, request, obj=None):
    #     # add page不显示BillInline
    #     for inline in self.get_inline_instances(request, obj):
    #         if isinstance(inline, BillInline) and obj is None:
    #             continue
    #         if not obj.invoice_code:
    #             continue
    #         yield inline.get_formset(request, obj), inline

    def get_queryset(self, request):
        # 只允许管理员和拥有该模型删除权限的人员，销售总监才能查看所有
        haved_perm = False
        for group in request.user.groups.all():
            if (group.id == 7) or (group.id == 14) or (group.id == 5):  #财务总监，销售总监,财务部
                haved_perm=True
        qs = super(InvoiceAdmin, self).get_queryset(request)
        if request.user.is_superuser or request.user.has_perm('fm.delete_invoice') or haved_perm:
            return qs
        return qs.filter(invoice__contract__salesman=request.user)

    def get_list_filter(self, request):
        #销售总监，admin，有删除权限的人可以看到salelistFilter
        haved_perm = False
        for group in request.user.groups.all():
            if group.id == 7 or group.id == 5 or group.id == 14:#财务总监，财务部，市场总监
                haved_perm=True
        if request.user.is_superuser or haved_perm:
            return [
                SaleListFilter,
                'invoice__contract__type',
                ('income_date', DateRangeFilter),
                ('date', DateRangeFilter)
            ]
        return [
            'invoice__contract__type',
            ('income_date', DateRangeFilter),
            ('date', DateRangeFilter)
        ]

    def lookup_allowed(self, lookup, *args, **kwargs):
        if lookup == 'invoice__contract__type__exact':
            return True
        return super(InvoiceAdmin, self).lookup_allowed(lookup, *args, **kwargs)

    # def change_view(self, request, object_id, form_url='', extra_context=None):
    #     extra_context = extra_context or {}
    #     extra_context['show_delete'] = False
    #     print(extra_context)
    #     print(request.user.has_perm('fm.add_invoice'))
    #     # if not Invoice.objects.get(id=object_id).invoice_code and not request.user.has_perm('fm.add_invoice'):
    #     #     extra_context['show_save'] = False
    #     #     extra_context['show_save_as_new'] = False
    #     #     extra_context['show_save_and_continue'] = False
    #     return super(InvoiceAdmin, self).change_view(request, object_id, form_url, extra_context=extra_context)


class BillChangeList(ChangeList):
    '''
    进账的ChangeList页面的统计
    '''
    def get_results(self, *args, **kwargs):
        super(BillChangeList, self).get_results(*args, **kwargs)
        q = self.result_list.aggregate(Sum('income'))
        self.income_count = q['income__sum']


class BillAdmin(admin.ModelAdmin):
    '''进账的Admin'''
    list_display = ('invoice', 'income', 'date')
    raw_id_fields = ['invoice']
    date_hierarchy = 'date'

    def get_changelist(self, request):
        return BillChangeList

    def save_model(self, request, obj, form, change):
        """
        1、无发票单号不能登记
        2、进账必须大于0
        3、进账总额不能超过开票金额
        """
        invoice_amount = obj.invoice.invoice.invoice.invoice.amount
        current_invoice_amounts = Bill.objects.filter(invoice=obj.invoice).exclude(id=obj.id).values_list('income', flat=True)
        sum_income = obj.income + sum(current_invoice_amounts)
        if not obj.invoice.invoice_code:
            messages.set_level(request, messages.WARNING)
            self.message_user(request, '不能对无单号发票登记进账', level=messages.WARNING)
        elif obj.income <= 0:
            messages.set_level(request, messages.ERROR)
            self.message_user(request, '进账登记必须大于零', level=messages.ERROR)
        elif invoice_amount < sum_income:
            messages.set_level(request, messages.ERROR)
            self.message_user(request, '进账总额 %.2f 超过开票金额 %.2f' % (sum_income, invoice_amount), level=messages.ERROR)
        else:
            obj.save()

BMS_admin_site.register(Invoice, InvoiceAdmin)
# admin.site.register(Bill, BillAdmin)
