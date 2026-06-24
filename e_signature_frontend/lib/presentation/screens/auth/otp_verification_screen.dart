import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:pinput/pinput.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:provider/provider.dart';
import '../../../core/constants/api_constants.dart';
import '../../providers/auth_provider.dart';
import '../../../theme/app_colors.dart';
import '../home_screen.dart';
import 'login_screen.dart';

class OtpVerificationScreen extends StatefulWidget {
  final String email;
  final String? phoneNumber;
  final bool sendOnOpen;
  final bool goHomeAfterVerification;

  const OtpVerificationScreen({
    super.key,
    required this.email,
    this.phoneNumber,
    this.sendOnOpen = false,
    this.goHomeAfterVerification = false,
  });

  @override
  State<OtpVerificationScreen> createState() => _OtpVerificationScreenState();
}

class _OtpVerificationScreenState extends State<OtpVerificationScreen> {
  final otpController = TextEditingController();
  bool _isLoading = false;
  bool _isSendingOtp = false;
  bool _otpSentOnOpen = false;
  final String _apiUrl = "${ApiConstants.baseUrl}/otp/verify";

  @override
  void initState() {
    super.initState();

    if (widget.sendOnOpen) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _sendOtp();
      });
    }
  }

  Future<void> _sendOtp() async {
    if (_isSendingOtp) return;

    setState(() => _isSendingOtp = true);

    bool sent = false;
    final phoneNumber = widget.phoneNumber;
    final email = widget.email.isNotEmpty
        ? widget.email
        : Provider.of<AuthProvider>(context, listen: false).userEmail ?? '';

    // Round-trip da solicitação do código (rede + geração no servidor +
    // enfileiramento na Twilio). NÃO inclui a entrega via WhatsApp (terceiro):
    // o tempo isolado do envio à Twilio é medido no backend
    // ("[TEMPO] Envio do OTP para a Twilio").
    final otpSw = Stopwatch()..start();
    if (phoneNumber != null && phoneNumber.isNotEmpty) {
      final response = await http.post(
        Uri.parse("${ApiConstants.baseUrl}/otp/generate"),
        headers: {"Content-Type": "application/json"},
        body: json.encode({
          "email": email,
          "phone_number": phoneNumber,
        }),
      );
      sent = response.statusCode == 200;
    } else {
      final authProvider = Provider.of<AuthProvider>(context, listen: false);
      sent = await authProvider.generateOtpForCurrentUser();
    }
    otpSw.stop();
    debugPrint(
      '[TEMPO] Geração do Código OTP (round-trip até sucesso=$sent) '
      'levou ${otpSw.elapsedMilliseconds} ms',
    );

    if (!mounted) return;

    setState(() {
      _isSendingOtp = false;
      _otpSentOnOpen = _otpSentOnOpen || sent;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: sent ? Colors.green : Colors.redAccent,
        content: Text(
          sent
              ? 'Código enviado para o seu WhatsApp.'
              : 'Não foi possível enviar o código OTP.',
        ),
      ),
    );
  }

  Future<void> _verifyOtp() async {
    if (otpController.text.length != 6) return;

    setState(() => _isLoading = true);

    try {
      final email = widget.email.isNotEmpty
          ? widget.email
          : Provider.of<AuthProvider>(context, listen: false).userEmail ?? '';

      final response = await http.post(
        Uri.parse(_apiUrl),
        headers: {"Content-Type": "application/json"},
        body: json.encode({
          "email": email,
          "code": otpController.text,
        }),
      );

      if (response.statusCode == 200) {
        await Provider.of<AuthProvider>(context, listen: false)
            .refreshCurrentUser();

        if (!mounted) return;

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            backgroundColor: Colors.green,
            content: Text('Verificação concluída com sucesso!')),
        );

        if (widget.goHomeAfterVerification) {
          Navigator.of(context).pushAndRemoveUntil(
            MaterialPageRoute(builder: (context) => const HomeScreen()),
            (route) => false,
          );
          return;
        }
        
        Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => LoginScreen(),
            ),
          );
   
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
           SnackBar(
            backgroundColor: Colors.redAccent,
            content: Text('Erro: ${response.body}')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Erro de conexão: $e"), backgroundColor: Colors.red),
      );
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Center(
        child: LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth > 500) {
              return _buildWideLayout();
            } else {
              return _buildNarrowLayout();
            }
          },
        ),
      ),
    );
  }

  Widget _buildWideLayout() {
    return Row(
      children: [
        Expanded(
          flex: 5,
          child: _buildFormSide(),
        ),
        Expanded(
          flex: 4,
          child: _buildImageSide(),
        ),
      ],
    );
  }

  Widget _buildNarrowLayout() {
    return SingleChildScrollView(
      child: Column(
        children: [
          const SizedBox(height: 40), 
          _buildFormSide(),
          const SizedBox(height: 40),
          _buildImageSide(),
        ],
      ),
    );
  }

  Widget _buildImageSide() {
    return Padding(
      padding: const EdgeInsets.all(20.0),
      child: Opacity(
        opacity: 0.8, 
        child: Image.asset(
          'assets/images/assinatura_garota_perfil.png',
          fit: BoxFit.contain,
          height: 450,
        ),
      ),
    );
  }

  Widget _buildFormSide() {
    final defaultPinTheme = PinTheme(
      width: 56,
      height: 60,
      textStyle: GoogleFonts.poppins(
        fontSize: 22, 
        color: AppColors.primaryText,
        fontWeight: FontWeight.w600
      ),
      decoration: BoxDecoration(
        color: AppColors.textFieldFill, 
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.textFieldBorder),
      ),
    );

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 40.0, vertical: 20.0),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Verificação',
            style: GoogleFonts.poppins(
              fontSize: 42,
              fontWeight: FontWeight.bold,
              color: AppColors.primaryText,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Digite o código enviado para o seu WhatsApp.',
            style: GoogleFonts.poppins(
              fontSize: 16,
              color: AppColors.primaryText.withValues(alpha: 0.7),
            ),
          ),
          if (_isSendingOtp || _otpSentOnOpen)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(
                _isSendingOtp
                    ? 'Enviando código...'
                    : 'Código enviado. Ele expira em 5 minutos.',
                style: GoogleFonts.poppins(
                  fontSize: 13,
                  color: AppColors.primaryText.withValues(alpha: 0.65),
                ),
              ),
            ),
          const SizedBox(height: 40),
          
          Center(
            child: Pinput(
              length: 6,
              controller: otpController,
              defaultPinTheme: defaultPinTheme,
              focusedPinTheme: defaultPinTheme.copyWith(
                decoration: defaultPinTheme.decoration!.copyWith(
                  border: Border.all(color: AppColors.primaryButton, width: 2),
                ),
              ),
              onCompleted: (pin) => _verifyOtp(),
            ),
          ),
          
          const SizedBox(height: 40),
          
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isLoading ? null : _verifyOtp,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryButton,
                padding: const EdgeInsets.symmetric(vertical: 20),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                foregroundColor: Colors.white,
              ),
              child: _isLoading 
                ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)) 
                : Text(
                  'Validar Código',
                  style: GoogleFonts.poppins(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ),
          ),
          const SizedBox(height: 24),
          Center(
            child: TextButton(
              onPressed: _isSendingOtp ? null : _sendOtp,
              child: Text(
                "Não recebeu? Reenviar",
                style: GoogleFonts.poppins(color: AppColors.primaryButton),
              ),
            ),
          )
        ],
      ),
    );
  }
}
