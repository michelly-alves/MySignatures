import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:file_picker/file_picker.dart';
import '../../../theme/app_colors.dart';
import '../../../data/repositories/document_repository.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';

class _SignerEntry {
  final UniqueKey key = UniqueKey();
  final TextEditingController fullName = TextEditingController();
  final TextEditingController nationalId = TextEditingController();
  final TextEditingController phone = TextEditingController();
  final TextEditingController email = TextEditingController();
  PlatformFile? photo;

  void dispose() {
    fullName.dispose();
    nationalId.dispose();
    phone.dispose();
    email.dispose();
  }
}

class CreateDocumentScreen extends StatefulWidget {
  const CreateDocumentScreen({super.key});

  @override
  State<CreateDocumentScreen> createState() => _CreateDocumentScreenState();
}

class _CreateDocumentScreenState extends State<CreateDocumentScreen> {
  final _formKey = GlobalKey<FormState>();
  final _documentRepository = DocumentRepository();

  final List<_SignerEntry> _signers = [_SignerEntry()];
  PlatformFile? _pickedDocumentFile;

  @override
  void dispose() {
    for (final signer in _signers) {
      signer.dispose();
    }
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

  String? _validateCpf(String? v) {
    if (v == null || v.trim().isEmpty) return 'Campo obrigatório';
    final digits = v.replaceAll(RegExp(r'\D'), '');
    if (digits.length != 11) return 'CPF deve ter 11 dígitos';
    if (RegExp(r'^(\d)\1+$').hasMatch(digits)) return 'CPF inválido';
    int sum = 0;
    for (int i = 0; i < 9; i++) {
      sum += int.parse(digits[i]) * (10 - i);
    }
    int rem = (sum * 10) % 11;
    if (rem == 10 || rem == 11) rem = 0;
    if (rem != int.parse(digits[9])) return 'CPF inválido';
    sum = 0;
    for (int i = 0; i < 10; i++) {
      sum += int.parse(digits[i]) * (11 - i);
    }
    rem = (sum * 10) % 11;
    if (rem == 10 || rem == 11) rem = 0;
    if (rem != int.parse(digits[10])) return 'CPF inválido';
    return null;
  }

  Future<void> _pickDocument() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
      withData: true,
    );
    if (result != null) {
      setState(() => _pickedDocumentFile = result.files.first);
    }
  }

  Future<void> _pickPhotoFor(_SignerEntry entry) async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.image,
      withData: true,
    );
    if (result != null) {
      setState(() => entry.photo = result.files.first);
    }
  }

  void _addSigner() {
    setState(() => _signers.add(_SignerEntry()));
  }

  void _removeSigner(_SignerEntry entry) {
    setState(() {
      _signers.remove(entry);
      entry.dispose();
    });
  }

  Future<void> _createDocument() async {
    if (_pickedDocumentFile == null) {
      _snack('Anexe o arquivo PDF do documento.', Colors.redAccent);
      return;
    }
    if (!_formKey.currentState!.validate()) {
      _snack('Corrija os campos destacados antes de continuar.', Colors.orange);
      return;
    }
    final missingPhoto = _signers.any((s) => s.photo == null);
    if (missingPhoto) {
      _snack('Anexe a foto de identificação de cada signatário.', Colors.redAccent);
      return;
    }

    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final token = authProvider.token;
    final companyId = authProvider.companyId;
    if (token == null || companyId == null) {
      _snack('Erro de autenticação. Faça login novamente.', Colors.redAccent);
      return;
    }

    final signersPayload = [
      for (final s in _signers)
        {
          'full_name': s.fullName.text.trim(),
          'phone_number': s.phone.text.trim(),
          'email': s.email.text.trim(),
          'national_id': s.nationalId.text.replaceAll(RegExp(r'\D'), ''),
        }
    ];
    final photosPayload = <({String name, Uint8List bytes})>[
      for (final s in _signers) (name: s.photo!.name, bytes: s.photo!.bytes!)
    ];

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    final navigator = Navigator.of(context);
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final error = await _documentRepository.createDocumentWithSigners(
      companyId: companyId,
      documentFileName: _pickedDocumentFile!.name,
      documentFileBytes: _pickedDocumentFile!.bytes!,
      signers: signersPayload,
      photos: photosPayload,
    );

    navigator.pop();

    if (error == null) {
      scaffoldMessenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.green,
        content: Text('Documento enviado com sucesso!'),
      ));
      navigator.pop();
    } else if (_isPhotoQualityError(error)) {
      await _showPhotoErrorDialog(_friendlyBackendError(error));
    } else {
      scaffoldMessenger.showSnackBar(SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text(_friendlyBackendError(error)),
        duration: const Duration(seconds: 4),
      ));
    }
  }

  bool _isPhotoQualityError(String raw) {
    final lower = raw.toLowerCase();
    return lower.contains('biometria') ||
        lower.contains('rosto') ||
        lower.contains('foto');
  }

  Future<void> _showPhotoErrorDialog(String message) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        icon: const Icon(Icons.image_not_supported_outlined,
            color: Colors.redAccent, size: 40),
        title: Text(
          'Problema com a foto',
          style: GoogleFonts.poppins(fontWeight: FontWeight.bold),
        ),
        content: Text(
          message,
          style: GoogleFonts.poppins(fontSize: 14),
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primaryButton,
              foregroundColor: Colors.white,
              shape:
                  RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: const Text('Entendi'),
          ),
        ],
      ),
    );
  }

  void _snack(String message, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: color,
      content: Text(message),
    ));
  }

  String _friendlyBackendError(String raw) {
    final lower = raw.toLowerCase();
    if (lower.contains('repetido')) {
      return 'Há CPFs repetidos entre os signatários.';
    }
    if (lower.contains('email') &&
        (lower.contains('já') || lower.contains('pertence'))) {
      return 'E-mail de um signatário já pertence a outro tipo de usuário.';
    }
    if (lower.contains('cpf') || lower.contains('national_id')) {
      return 'CPF de um signatário inválido ou já cadastrado para outra pessoa.';
    }
    if (lower.contains('telefone') || lower.contains('phone')) {
      return 'Número de telefone inválido.';
    }
    return raw;
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
          onPressed: () => Navigator.of(context).pop(),
        ),
        title: Text('Criar Novo Documento',
            style: GoogleFonts.poppins(
                color: AppColors.primaryText, fontWeight: FontWeight.bold)),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _sectionTitle('1. Documento para Assinatura'),
              const SizedBox(height: 16),
              _buildDocumentUpload(),

              const SizedBox(height: 32),

              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _sectionTitle('2. Signatários'),
                  Text(
                    '${_signers.length}',
                    style: GoogleFonts.poppins(
                      color: AppColors.primaryButton,
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Todos assinam o mesmo documento. A conclusão só ocorre quando '
                'todos tiverem assinado.',
                style: GoogleFonts.poppins(
                    fontSize: 13, color: AppColors.primaryText.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),

              ..._signers.asMap().entries.map(
                    (e) => _buildSignerCard(e.value, e.key + 1),
                  ),

              const SizedBox(height: 4),
              OutlinedButton.icon(
                onPressed: _addSigner,
                icon: const Icon(Icons.person_add_alt_1),
                label: const Text('Adicionar signatário'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primaryButton,
                  minimumSize: const Size(double.infinity, 50),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  side: const BorderSide(color: AppColors.primaryButton),
                ),
              ),

              const SizedBox(height: 32),
              _buildSubmitButton(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _sectionTitle(String title) => Text(title,
      style: GoogleFonts.poppins(
          fontSize: 22, fontWeight: FontWeight.bold, color: AppColors.primaryText));

  Widget _buildSignerCard(_SignerEntry entry, int index) {
    return Container(
      key: entry.key,
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.textFieldBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Signatário $index',
                  style: GoogleFonts.poppins(
                      fontWeight: FontWeight.w600,
                      fontSize: 16,
                      color: AppColors.primaryText)),
              const Spacer(),
              if (_signers.length > 1)
                IconButton(
                  icon: const Icon(Icons.delete_outline, color: Colors.redAccent),
                  tooltip: 'Remover signatário',
                  onPressed: () => _removeSigner(entry),
                ),
            ],
          ),
          const SizedBox(height: 8),
          _buildTextField(
            controller: entry.fullName,
            label: 'Nome Completo',
            validator: _validateRequired,
          ),
          const SizedBox(height: 12),
          _buildTextField(
            controller: entry.nationalId,
            label: 'CPF',
            hint: '000.000.000-00',
            keyboardType: TextInputType.number,
            validator: _validateCpf,
          ),
          const SizedBox(height: 12),
          _buildTextField(
            controller: entry.phone,
            label: 'Telefone (com DDD)',
            hint: '85999999999',
            keyboardType: TextInputType.phone,
            validator: _validatePhone,
          ),
          const SizedBox(height: 12),
          _buildTextField(
            controller: entry.email,
            label: 'E-mail',
            keyboardType: TextInputType.emailAddress,
            validator: _validateEmail,
          ),
          const SizedBox(height: 12),
          _buildPhotoUpload(entry),
        ],
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    String? hint,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      validator: validator,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        hintStyle: TextStyle(color: Colors.grey[400]),
        filled: true,
        fillColor: AppColors.textFieldFill,
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
            borderSide: const BorderSide(color: Colors.redAccent)),
        focusedErrorBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Colors.redAccent, width: 2)),
        contentPadding: const EdgeInsets.symmetric(vertical: 16, horizontal: 16),
      ),
    );
  }

  Widget _buildDocumentUpload() {
    final file = _pickedDocumentFile;
    if (file != null) {
      return _filePill(
        icon: Icons.picture_as_pdf,
        iconColor: Colors.red,
        name: file.name,
        onRemove: () => setState(() => _pickedDocumentFile = null),
      );
    }
    return OutlinedButton.icon(
      icon: const Icon(Icons.upload_file_outlined),
      label: const Text('Selecionar Arquivo PDF'),
      onPressed: _pickDocument,
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primaryButton,
        minimumSize: const Size(double.infinity, 50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        side: const BorderSide(color: AppColors.primaryButton),
      ),
    );
  }

  Widget _buildPhotoUpload(_SignerEntry entry) {
    final file = entry.photo;
    if (file != null) {
      return _filePill(
        icon: Icons.image,
        iconColor: AppColors.primaryButton,
        name: file.name,
        onRemove: () => setState(() => entry.photo = null),
      );
    }
    return OutlinedButton.icon(
      icon: const Icon(Icons.add_a_photo_outlined),
      label: const Text('Foto de identificação'),
      onPressed: () => _pickPhotoFor(entry),
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primaryButton,
        minimumSize: const Size(double.infinity, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        side: const BorderSide(color: AppColors.primaryButton),
      ),
    );
  }

  Widget _filePill({
    required IconData icon,
    required Color iconColor,
    required String name,
    required VoidCallback onRemove,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.textFieldFill,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.textFieldBorder),
      ),
      child: Row(
        children: [
          Icon(icon, color: iconColor),
          const SizedBox(width: 12),
          Expanded(
            child: Text(name,
                style: GoogleFonts.poppins(), overflow: TextOverflow.ellipsis),
          ),
          IconButton(
            icon: const Icon(Icons.close, size: 20),
            onPressed: onRemove,
          ),
        ],
      ),
    );
  }

  Widget _buildSubmitButton() {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton.icon(
        onPressed: _createDocument,
        icon: const Icon(Icons.send_outlined),
        label: Text('Criar e Enviar',
            style: GoogleFonts.poppins(fontWeight: FontWeight.w600)),
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primaryButton,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
    );
  }
}
