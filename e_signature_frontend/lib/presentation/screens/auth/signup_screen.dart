import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../../core/constants/api_constants.dart';
import '../../../core/utils/password_validator.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../../theme/app_colors.dart';
import 'otp_verification_screen.dart';

class SignUpScreen extends StatefulWidget {
  const SignUpScreen({super.key});

  @override
  State<SignUpScreen> createState() => _SignUpScreenState();
}

class _SignUpScreenState extends State<SignUpScreen> {
  final _formKey = GlobalKey<FormState>();
  bool _isLoading = false;
  final Map<TextEditingController, bool> _obscure = {};

  final _authRepository = AuthRepository();

  final companyNameController    = TextEditingController();
  final cnpjController           = TextEditingController();
  final companyEmailController   = TextEditingController();
  final companyPhoneController   = TextEditingController();
  final companyPasswordController = TextEditingController();

  @override
  void dispose() {
    companyNameController.dispose();
    cnpjController.dispose();
    companyEmailController.dispose();
    companyPhoneController.dispose();
    companyPasswordController.dispose();
    super.dispose();
  }

  String? _validateRequired(String? v) =>
      (v == null || v.trim().isEmpty) ? 'Campo obrigatório' : null;

  String? _validateEmail(String? v) {
    if (v == null || v.trim().isEmpty) return 'Campo obrigatório';
    final ok = RegExp(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        .hasMatch(v.trim());
    return ok ? null : 'E-mail inválido';
  }

  String? _validatePhone(String? v) {
    if (v == null || v.trim().isEmpty) return 'Campo obrigatório';
    final digits = v.replaceAll(RegExp(r'\D'), '');
    if (digits.length < 10 || digits.length > 13) {
      return 'Telefone inválido — inclua DDD (ex: 85999999999)';
    }
    return null;
  }

  String? _validatePassword(String? v) => PasswordValidator.validate(v);

  String? _validateCnpj(String? v) {
    if (v == null || v.trim().isEmpty) return 'Campo obrigatório';
    final digits = v.replaceAll(RegExp(r'\D'), '');
    if (digits.length != 14) return 'CNPJ deve ter 14 dígitos';
    if (RegExp(r'^(\d)\1+$').hasMatch(digits)) return 'CNPJ inválido';

    const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];

    int sum = 0;
    for (int i = 0; i < 12; i++) {
      sum += int.parse(digits[i]) * w1[i];
    }
    int rem = sum % 11;
    if ((rem < 2 ? 0 : 11 - rem) != int.parse(digits[12])) return 'CNPJ inválido';

    sum = 0;
    for (int i = 0; i < 13; i++) {
      sum += int.parse(digits[i]) * w2[i];
    }
    rem = sum % 11;
    if ((rem < 2 ? 0 : 11 - rem) != int.parse(digits[13])) return 'CNPJ inválido';

    return null;
  }

  Future<void> _register() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final error = await _authRepository.createUser({
      'email': companyEmailController.text.trim(),
      'password': companyPasswordController.text,
      'role': 0,
      'legal_name': companyNameController.text.trim(),
      'tax_id': cnpjController.text.replaceAll(RegExp(r'\D'), ''),
      'phone_number': companyPhoneController.text.trim(),
    });

    if (!mounted) return;

    if (error == null) {
      try {
        final otpResponse = await http.post(
          Uri.parse('${ApiConstants.baseUrl}/otp/generate'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({
            'email': companyEmailController.text.trim(),
            'phone_number': companyPhoneController.text.trim(),
          }),
        );

        if (!mounted) return;

        bool otpSent = false;
        if (otpResponse.statusCode == 200) {
          try {
            final body = json.decode(otpResponse.body) as Map<String, dynamic>;
            otpSent = body['expires_at'] != null;
          } catch (_) {
            otpSent = false;
          }
        }

        if (otpSent) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => OtpVerificationScreen(
                email: companyEmailController.text.trim(),
                phoneNumber: companyPhoneController.text.trim(),
              ),
            ),
          );
        } else {
          scaffoldMessenger.showSnackBar(const SnackBar(
            backgroundColor: Colors.orange,
            content: Text('Conta criada, mas não foi possível enviar o código por WhatsApp. Contate o suporte.'),
          ));
        }
      } catch (_) {
        scaffoldMessenger.showSnackBar(const SnackBar(
          backgroundColor: Colors.orange,
          content: Text('Conta criada, mas erro ao enviar OTP. Contate o suporte.'),
        ));
      }
    } else {
      final msg = _friendlyBackendError(error);
      scaffoldMessenger.showSnackBar(SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text(msg),
        duration: const Duration(seconds: 4),
      ));
    }

    if (mounted) setState(() => _isLoading = false);
  }

  String _friendlyBackendError(String raw) {
    final lower = raw.toLowerCase();
    if (lower.contains('email') && (lower.contains('já') || lower.contains('duplicado') || lower.contains('existe'))) {
      return 'E-mail já cadastrado. Use outro e-mail ou faça login.';
    }
    if (lower.contains('cnpj') || lower.contains('tax_id')) {
      return 'CNPJ já cadastrado ou inválido.';
    }
    if (lower.contains('telefone') || lower.contains('phone')) {
      return 'Número de telefone inválido ou já cadastrado.';
    }
    return raw;
  }


  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: LayoutBuilder(
        builder: (context, constraints) => constraints.maxWidth > 900
            ? _buildWideLayout()
            : _buildNarrowLayout(),
      ),
    );
  }

  Widget _buildWideLayout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(flex: 5, child: _buildWideFormPanel()),
        Expanded(flex: 4, child: _buildImageSide()),
      ],
    );
  }

  Widget _buildWideFormPanel() {
    return Stack(
      children: [
        Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 80),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: _buildFormContent(),
            ),
          ),
        ),
        Positioned(
          top: 24,
          left: 24,
          child: IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
            padding: EdgeInsets.zero,
          ),
        ),
      ],
    );
  }

  Widget _buildNarrowLayout() {
    return SingleChildScrollView(
      child: Column(
        children: [
          _buildFormSide(),
          const SizedBox(height: 40),
          _buildImageSide(),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildFormContent() {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Cadastre-se',
              style: GoogleFonts.poppins(
                  fontSize: 40, fontWeight: FontWeight.bold, color: AppColors.primaryText)),
          const SizedBox(height: 8),
          Text('Crie sua conta para começar a assinar documentos.',
              style: GoogleFonts.poppins(
                  fontSize: 15, color: AppColors.primaryText.withValues(alpha: 0.6))),
          const SizedBox(height: 32),
          _buildEmpresaForm(),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isLoading ? null : _register,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryButton,
                padding: const EdgeInsets.symmetric(vertical: 20),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                foregroundColor: Colors.white,
                disabledBackgroundColor: AppColors.primaryButton.withValues(alpha: 0.6),
              ),
              child: _isLoading
                  ? const SizedBox(
                      height: 24, width: 24,
                      child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                  : Text('Cadastrar',
                      style: GoogleFonts.poppins(fontSize: 18, fontWeight: FontWeight.w600)),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFormSide() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
            padding: EdgeInsets.zero,
            alignment: Alignment.centerLeft,
          ),
          const SizedBox(height: 16),
          _buildFormContent(),
        ],
      ),
    );
  }

  Widget _buildImageSide() {
    return Container(
      color: AppColors.primaryButton.withValues(alpha: 0.10),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(40.0),
          child: Image.asset('assets/images/assinatura_garota_perfil.png',
              fit: BoxFit.contain, height: 450),
        ),
      ),
    );
  }

  Widget _buildEmpresaForm() {
    return Column(
      children: [
        _buildField(
          controller: companyNameController,
          label: 'Nome fantasia',
          validator: _validateRequired,
        ),
        const SizedBox(height: 16),
        _buildField(
          controller: cnpjController,
          label: 'CNPJ',
          hint: '00.000.000/0001-00',
          keyboardType: TextInputType.number,
          validator: _validateCnpj,
        ),
        const SizedBox(height: 16),
        _buildField(
          controller: companyPhoneController,
          label: 'Celular Responsável (com DDD)',
          hint: '+55 85 99999-9999',
          keyboardType: TextInputType.phone,
          validator: _validatePhone,
        ),
        const SizedBox(height: 16),
        _buildField(
          controller: companyEmailController,
          label: 'E-mail da Empresa',
          keyboardType: TextInputType.emailAddress,
          validator: _validateEmail,
        ),
        const SizedBox(height: 16),
        _buildField(
          controller: companyPasswordController,
          label: 'Senha',
          isPassword: true,
          validator: _validatePassword,
        ),
      ],
    );
  }

  Widget _buildField({
    required TextEditingController controller,
    required String label,
    String? hint,
    bool isPassword = false,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    final obscure = _obscure[controller] ?? true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: GoogleFonts.poppins(
                color: AppColors.primaryText.withValues(alpha: 0.8),
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        TextFormField(
          controller: controller,
          obscureText: isPassword && obscure,
          keyboardType: keyboardType,
          validator: validator,
          autovalidateMode: AutovalidateMode.onUserInteraction,
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: TextStyle(color: Colors.grey[400]),
            filled: true,
            fillColor: AppColors.textFieldFill,
            suffixIcon: isPassword
                ? IconButton(
                    icon: Icon(
                      obscure
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                      color: Colors.grey,
                    ),
                    onPressed: () =>
                        setState(() => _obscure[controller] = !obscure),
                  )
                : null,
            border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.textFieldBorder)),
            enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.textFieldBorder)),
            focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppColors.primaryButton, width: 2)),
            errorBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.redAccent, width: 1)),
            focusedErrorBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: Colors.redAccent, width: 2)),
            contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
          ),
        ),
      ],
    );
  }
}
