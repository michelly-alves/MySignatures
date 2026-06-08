import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:http/http.dart' as http;

import '../../../core/constants/api_constants.dart';
import '../../../theme/app_colors.dart';

class SignatureValidationScreen extends StatefulWidget {
  final String? initialCode;

  const SignatureValidationScreen({super.key, this.initialCode});

  @override
  State<SignatureValidationScreen> createState() =>
      _SignatureValidationScreenState();
}

class _SignatureValidationScreenState extends State<SignatureValidationScreen> {
  final TextEditingController _codeController = TextEditingController();
  bool _loading = false;
  Map<String, dynamic>? _result;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.initialCode != null && widget.initialCode!.isNotEmpty) {
      _codeController.text = widget.initialCode!;
      WidgetsBinding.instance.addPostFrameCallback((_) => _validate());
    }
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _validate() async {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      setState(() => _error = 'Informe o código de validação.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });

    try {
      final response = await http.get(
        Uri.parse('${ApiConstants.baseUrl}/public/signatures/$code'),
        headers: {'Content-Type': 'application/json'},
      );

      if (!mounted) return;

      if (response.statusCode == 200) {
        setState(() => _result = jsonDecode(response.body) as Map<String, dynamic>);
      } else if (response.statusCode == 404) {
        setState(() => _error = 'Nenhuma assinatura encontrada com este código.');
      } else {
        setState(() => _error = 'Erro ao consultar (código ${response.statusCode}).');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Erro de conexão. Verifique sua internet.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _copyToClipboard(String text, String label) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: Colors.green.shade700,
      content: Text('$label copiado para a área de transferência.'),
      duration: const Duration(seconds: 2),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: AppColors.primaryText),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: Text(
          'Validar Assinatura',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildHeader(),
                const SizedBox(height: 24),
                _buildSearchCard(),
                const SizedBox(height: 24),
                if (_error != null) _buildErrorCard(),
                if (_result != null) _buildResultView(_result!),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Verificar autenticidade',
          style: GoogleFonts.poppins(
            fontSize: 26,
            fontWeight: FontWeight.bold,
            color: AppColors.primaryText,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Informe o código de validação que aparece no documento assinado para '
          'confirmar a autenticidade da assinatura e a integridade do documento.',
          style: GoogleFonts.poppins(
            fontSize: 14,
            color: AppColors.primaryText.withValues(alpha: 0.7),
          ),
        ),
      ],
    );
  }

  Widget _buildSearchCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: _cardDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Código de validação',
            style: GoogleFonts.poppins(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: AppColors.primaryText.withValues(alpha: 0.8),
            ),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _codeController,
            onSubmitted: (_) => _validate(),
            decoration: InputDecoration(
              hintText: 'SIG-XXXXXXXXXXXXXXXX',
              hintStyle: TextStyle(color: Colors.grey[400], letterSpacing: 1.2),
              filled: true,
              fillColor: AppColors.textFieldFill,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.textFieldBorder),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.textFieldBorder),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: AppColors.primaryButton, width: 2),
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            ),
            style: GoogleFonts.robotoMono(fontSize: 14, letterSpacing: 1.0),
          ),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _loading ? null : _validate,
              icon: _loading
                  ? const SizedBox(
                      width: 18, height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.verified_outlined),
              label: Text(
                _loading ? 'Verificando...' : 'Verificar',
                style: GoogleFonts.poppins(fontWeight: FontWeight.w600, fontSize: 15),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryButton,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.red.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: Colors.red.shade700),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _error!,
              style: GoogleFonts.poppins(color: Colors.red.shade800, fontSize: 14),
            ),
          ),
        ],
      ),
    );
  }


  Widget _buildResultView(Map<String, dynamic> data) {
    final bool valid = data['valido'] == true;
    final assinante = (data['signatario'] ?? {}) as Map<String, dynamic>;
    final assinadoEm = (data['assinado_em'] ?? {}) as Map<String, dynamic>;
    final documento = (data['documento'] ?? {}) as Map<String, dynamic>;
    final evento = (data['evento_de_assinatura'] ?? {}) as Map<String, dynamic>;
    final prova = (data['prova_tecnica'] ?? {}) as Map<String, dynamic>;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildStatusBanner(valid, data['status']?.toString() ?? '',
            data['mensagem']?.toString() ?? ''),
        const SizedBox(height: 16),
        _buildInfoCard(
          title: 'Signatário',
          icon: Icons.person_outline,
          children: [
            _infoLine('Nome', assinante['nome']?.toString() ?? '—'),
            if (assinante['observacao'] != null)
              _infoNote(assinante['observacao'].toString()),
          ],
        ),
        const SizedBox(height: 16),
        _buildInfoCard(
          title: 'Assinado em',
          icon: Icons.event_outlined,
          children: [
            _infoLine('Data', assinadoEm['formatted']?.toString() ?? '—'),
            if (assinadoEm['iso'] != null)
              _infoLine('ISO 8601', assinadoEm['iso'].toString(),
                  copyable: true, copyLabel: 'Data ISO'),
          ],
        ),
        const SizedBox(height: 16),
        _buildInfoCard(
          title: 'Documento',
          icon: Icons.description_outlined,
          children: [
            _infoLine(
              'Algoritmo',
              documento['algoritmo_de_hash']?.toString() ?? '—',
            ),
            _infoLine(
              'Hash SHA-256',
              documento['hash_sha256']?.toString() ?? '—',
              copyable: true,
              copyLabel: 'Hash do documento',
              monospace: true,
            ),
            if (documento['observacao'] != null)
              _infoNote(documento['observacao'].toString()),
          ],
        ),
        const SizedBox(height: 16),
        _buildEventCard(evento),
        const SizedBox(height: 16),
        _buildInfoCard(
          title: 'Código de validação',
          icon: Icons.qr_code_2_outlined,
          children: [
            _infoLine(
              'Código',
              data['codigo_de_validacao']?.toString() ?? '—',
              copyable: true,
              copyLabel: 'Código',
              monospace: true,
            ),
          ],
        ),
        const SizedBox(height: 16),
        _buildTechnicalProof(prova),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _buildStatusBanner(bool valid, String status, String mensagem) {
    final color = valid ? Colors.green : Colors.red;
    final icon = valid ? Icons.verified_outlined : Icons.gpp_bad_outlined;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.4), width: 1.5),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: color.shade700, size: 28),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  status,
                  style: GoogleFonts.poppins(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: color.shade800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  mensagem,
                  style: GoogleFonts.poppins(
                    fontSize: 13,
                    color: AppColors.primaryText.withValues(alpha: 0.8),
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoCard({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: _cardDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.primaryButton, size: 20),
              const SizedBox(width: 8),
              Text(
                title,
                style: GoogleFonts.poppins(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: AppColors.primaryText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }

  Widget _infoLine(
    String label,
    String value, {
    bool copyable = false,
    bool monospace = false,
    String? copyLabel,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: GoogleFonts.poppins(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: AppColors.primaryText.withValues(alpha: 0.5),
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: SelectableText(
                  value,
                  style: monospace
                      ? GoogleFonts.robotoMono(
                          fontSize: 12,
                          color: AppColors.primaryText,
                          height: 1.4,
                        )
                      : GoogleFonts.poppins(
                          fontSize: 14,
                          color: AppColors.primaryText,
                        ),
                ),
              ),
              if (copyable) ...[
                const SizedBox(width: 8),
                InkWell(
                  borderRadius: BorderRadius.circular(6),
                  onTap: () => _copyToClipboard(value, copyLabel ?? label),
                  child: Padding(
                    padding: const EdgeInsets.all(4),
                    child: Icon(
                      Icons.copy_outlined,
                      size: 16,
                      color: AppColors.primaryButton,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _infoNote(String text) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: AppColors.primaryButton.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.info_outline,
                size: 14, color: AppColors.primaryButton.withValues(alpha: 0.7)),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                text,
                style: GoogleFonts.poppins(
                  fontSize: 11,
                  color: AppColors.primaryText.withValues(alpha: 0.6),
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEventCard(Map<String, dynamic> evento) {
    if (evento.isEmpty) return const SizedBox.shrink();

    return _buildInfoCard(
      title: 'Evento de assinatura',
      icon: Icons.fingerprint_outlined,
      children: [
        if (evento['descricao'] != null) _infoNote(evento['descricao'].toString()),
        if (evento['hash_composto_sha256'] != null)
          _infoLine(
            'Hash composto (SHA-256)',
            evento['hash_composto_sha256'].toString(),
            copyable: true,
            copyLabel: 'Hash composto',
            monospace: true,
          ),
        if (evento['assinado_em_iso_canonico'] != null)
          _infoLine(
            'Assinado em (ISO 8601 canônico)',
            evento['assinado_em_iso_canonico'].toString(),
            copyable: true,
            copyLabel: 'ISO canônico',
            monospace: true,
          ),
      ],
    );
  }

  Widget _buildTechnicalProof(Map<String, dynamic> prova) {
    final rsa = (prova['assinatura_rsa'] ?? {}) as Map<String, dynamic>;
    final acc = (prova['pertencimento_ao_acumulador'] ?? {}) as Map<String, dynamic>;

    return Container(
      decoration: _cardDecoration(),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          leading: Icon(Icons.code, color: AppColors.primaryButton, size: 20),
          title: Text(
            'Prova técnica',
            style: GoogleFonts.poppins(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: AppColors.primaryText,
            ),
          ),
          subtitle: Text(
            'Dados criptográficos para verificação independente',
            style: GoogleFonts.poppins(
              fontSize: 11,
              color: AppColors.primaryText.withValues(alpha: 0.6),
            ),
          ),
          children: [
            if (prova['descricao'] != null) ...[
              _infoNote(prova['descricao'].toString()),
              const SizedBox(height: 16),
            ],
            _buildSubsectionTitle('Assinatura RSA-PSS'),
            const SizedBox(height: 8),
            if (rsa['algoritmo'] != null)
              _infoLine('Algoritmo', rsa['algoritmo'].toString()),
            if (rsa['equacao_de_verificacao'] != null)
              _infoLine('Equação de verificação',
                  rsa['equacao_de_verificacao'].toString(),
                  monospace: true),
            if (rsa['signature_base64'] != null)
              _infoLine('Assinatura (Base64)', rsa['signature_base64'].toString(),
                  copyable: true, copyLabel: 'signature_base64', monospace: true),
            if (rsa['public_key_pem'] != null)
              _infoLine('Chave pública (PEM)', rsa['public_key_pem'].toString(),
                  copyable: true, copyLabel: 'public_key_pem', monospace: true),
            const SizedBox(height: 16),
            _buildSubsectionTitle('Pertencimento ao acumulador'),
            const SizedBox(height: 8),
            if (acc['descricao'] != null) _infoNote(acc['descricao'].toString()),
            if (acc['equacao_de_verificacao'] != null)
              _infoLine('Equação de verificação',
                  acc['equacao_de_verificacao'].toString(),
                  monospace: true),
            if (acc['acumulador_hex'] != null)
              _infoLine('Acumulador (hex)', acc['acumulador_hex'].toString(),
                  copyable: true, copyLabel: 'acumulador_hex', monospace: true),
            if (acc['modulo_n_hex'] != null)
              _infoLine('Módulo n (hex)', acc['modulo_n_hex'].toString(),
                  copyable: true, copyLabel: 'modulo_n_hex', monospace: true),
            if (acc['gerador_hex'] != null)
              _infoLine('Gerador (hex)', acc['gerador_hex'].toString(),
                  monospace: true),
            if (acc['x_hex'] != null)
              _infoLine('x (hex)', acc['x_hex'].toString(),
                  copyable: true, copyLabel: 'x_hex', monospace: true),
            if (acc['x_nonce'] != null)
              _infoLine('x_nonce', acc['x_nonce'].toString(), monospace: true),
            if (acc['witness_hex'] != null)
              _infoLine('Witness (hex)', acc['witness_hex'].toString(),
                  copyable: true, copyLabel: 'witness_hex', monospace: true),
          ],
        ),
      ),
    );
  }

  Widget _buildSubsectionTitle(String title) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.primaryButton.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        title,
        style: GoogleFonts.poppins(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: AppColors.primaryButton,
        ),
      ),
    );
  }

  BoxDecoration _cardDecoration() => BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      );
}
