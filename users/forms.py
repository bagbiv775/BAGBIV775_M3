from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from core.forms import StyledFormMixin
from orders.models import Order
from users.models import Address


class RegistrationForm(StyledFormMixin, UserCreationForm[User]):
    email = forms.EmailField(label='Email', required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def clean_email(self) -> str:
        email: str = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже зарегистрирован.')
        return email


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class ProfileForm(StyledFormMixin, forms.ModelForm[User]):
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email')

    def clean_email(self) -> str:
        email: str = self.cleaned_data['email'].strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Этот email уже используется другим пользователем.')
        return email


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class AddressForm(StyledFormMixin, forms.ModelForm[Address]):
    class Meta:
        model = Address
        fields = ('label', 'full_name', 'phone', 'city', 'address')


class OrderHistoryFilterForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(
        label='Статус',
        required=False,
        choices=[('', 'Все статусы'), *Order.Status.choices],
    )
