import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../../theme/app_colors.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _emailController = TextEditingController();
  final _authRepository = AuthRepository();

  bool _isLoading = false;
  bool _emailSent = false;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final email = _emailController.text.trim();
    if (email.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.redAccent,
          content: Text('Informe seu e-mail para continuar.'),
        ),
      );
      return;
    }

    setState(() => _isLoading = true);
    await _authRepository.requestPasswordReset(email);

    if (mounted) {
      setState(() {
        _isLoading = false;
        _emailSent = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth > 900) {
            return _buildWideLayout();
          } else {
            return _buildNarrowLayout();
          }
        },
      ),
    );
  }

  Widget _buildWideLayout() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Expanded(
          flex: 5,
          child: _buildWideFormPanel(),
        ),
        Expanded(
          flex: 4,
          child: _buildImageSide(),
        ),
      ],
    );
  }

  Widget _buildWideFormPanel() {
    return Stack(
      children: [
        // Formulário centralizado no painel inteiro
        Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 80),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 350),
                child: _emailSent ? _buildSuccessContent() : _buildFormContent(),
              ),
            ),
          ),
        ),
        // Seta de voltar fixada no topo-esquerdo
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
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 24, left: 16),
            child: IconButton(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
              padding: EdgeInsets.zero,
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 350),
              child: _emailSent ? _buildSuccessContent() : _buildFormContent(),
            ),
          ),
          const SizedBox(height: 32),
          _buildImageSide(),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  Widget _buildFormContent() {
    return Column(
      key: const ValueKey('form'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Esqueci minha\nsenha',
          style: GoogleFonts.poppins(
            fontSize: 40,
            fontWeight: FontWeight.bold,
            color: AppColors.primaryText,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Informe o e-mail cadastrado e enviaremos\n'
          'um link para criar uma nova senha.',
          style: GoogleFonts.poppins(
            fontSize: 15,
            color: AppColors.primaryText.withValues(alpha: 0.6),
          ),
        ),
        const SizedBox(height: 36),
        Text(
          'E-mail',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        TextFormField(
          controller: _emailController,
          keyboardType: TextInputType.emailAddress,
          autofocus: true,
          style: GoogleFonts.poppins(),
          decoration: InputDecoration(
            hintText: 'seu@email.com',
            hintStyle: GoogleFonts.poppins(
              color: Colors.grey[400],
              fontSize: 14,
            ),
            filled: true,
            fillColor: AppColors.textFieldFill,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: AppColors.textFieldBorder),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: AppColors.textFieldBorder),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide:
                  const BorderSide(color: AppColors.primaryButton, width: 2),
            ),
            contentPadding:
                const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
          ),
        ),
        const SizedBox(height: 28),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: _isLoading ? null : _submit,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryButton,
              padding: const EdgeInsets.symmetric(vertical: 20),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              foregroundColor: Colors.white,
              disabledBackgroundColor:
                  AppColors.primaryButton.withValues(alpha: 0.6),
            ),
            child: _isLoading
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                      color: Colors.white,
                      strokeWidth: 2,
                    ),
                  )
                : Text(
                    'Enviar link de redefinição',
                    style: GoogleFonts.poppins(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _buildSuccessContent() {
    return Column(
      key: const ValueKey('success'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Verifique seu\ne-mail',
          style: GoogleFonts.poppins(
            fontSize: 40,
            fontWeight: FontWeight.bold,
            color: AppColors.primaryText,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          'Se o endereço informado estiver cadastrado,\n'
          'você receberá um e-mail com o link para\n'
          'criar uma nova senha.',
          style: GoogleFonts.poppins(
            fontSize: 15,
            color: AppColors.primaryText.withValues(alpha: 0.6),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'O link expira em 1 hora.',
          style: GoogleFonts.poppins(
            fontSize: 13,
            color: AppColors.primaryText.withValues(alpha: 0.45),
            fontStyle: FontStyle.italic,
          ),
        ),
        const SizedBox(height: 36),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => Navigator.of(context).pop(),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryButton,
              padding: const EdgeInsets.symmetric(vertical: 20),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              foregroundColor: Colors.white,
            ),
            child: Text(
              'Voltar para o Login',
              style: GoogleFonts.poppins(
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Center(
          child: TextButton(
            onPressed: () => setState(() {
              _emailSent = false;
              _emailController.clear();
            }),
            child: Text(
              'Usar outro e-mail',
              style: GoogleFonts.poppins(
                color: AppColors.primaryText.withValues(alpha: 0.6),
                fontSize: 14,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildImageSide() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.primaryButton.withValues(alpha: 0.10),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(48),
          child: Image.asset(
            'assets/images/assinatura_garota_perfil.png',
            fit: BoxFit.contain,
            height: 460,
          ),
        ),
      ),
    );
  }
}
