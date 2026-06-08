import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:file_picker/file_picker.dart';
import '../../../theme/app_colors.dart';
import '../../../data/repositories/document_repository.dart';
import 'package:provider/provider.dart';
import '../../providers/auth_provider.dart';

class CreateDocumentScreen extends StatefulWidget {
  const CreateDocumentScreen({super.key});

  @override
  State<CreateDocumentScreen> createState() => _CreateDocumentScreenState();
}

class _CreateDocumentScreenState extends State<CreateDocumentScreen> {
  final _formKey = GlobalKey<FormState>();
  final _documentRepository = DocumentRepository();

  final _signerFullNameController    = TextEditingController();
  final _signerNationalIdController  = TextEditingController();
  final _signerPhoneNumberController = TextEditingController();
  final _signerEmailController       = TextEditingController();

  PlatformFile? _pickedDocumentFile;
  PlatformFile? _pickedPhotoIdFile;

  @override
  void dispose() {
    _signerFullNameController.dispose();
    _signerNationalIdController.dispose();
    _signerPhoneNumberController.dispose();
    _signerEmailController.dispose();
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

  String? _validateCpfOrCnpj(String? v) {
    if (v == null || v.trim().isEmpty) return 'Campo obrigatório';
    final digits = v.replaceAll(RegExp(r'\D'), '');
    if (digits.length == 11) return _cpfError(digits);
    if (digits.length == 14) return _cnpjError(digits);
    return 'Informe CPF (11 dígitos) ou CNPJ (14 dígitos)';
  }

  String? _cpfError(String digits) {
    if (RegExp(r'^(\d)\1+$').hasMatch(digits)) return 'CPF inválido';
    int sum = 0;
    for (int i = 0; i < 9; i++) { sum += int.parse(digits[i]) * (10 - i); }
    int rem = (sum * 10) % 11;
    if (rem == 10 || rem == 11) rem = 0;
    if (rem != int.parse(digits[9])) return 'CPF inválido';
    sum = 0;
    for (int i = 0; i < 10; i++) { sum += int.parse(digits[i]) * (11 - i); }
    rem = (sum * 10) % 11;
    if (rem == 10 || rem == 11) rem = 0;
    if (rem != int.parse(digits[10])) return 'CPF inválido';
    return null;
  }

  String? _cnpjError(String digits) {
    if (RegExp(r'^(\d)\1+$').hasMatch(digits)) return 'CNPJ inválido';
    const w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    int sum = 0;
    for (int i = 0; i < 12; i++) { sum += int.parse(digits[i]) * w1[i]; }
    int rem = sum % 11;
    if ((rem < 2 ? 0 : 11 - rem) != int.parse(digits[12])) return 'CNPJ inválido';
    sum = 0;
    for (int i = 0; i < 13; i++) { sum += int.parse(digits[i]) * w2[i]; }
    rem = sum % 11;
    if ((rem < 2 ? 0 : 11 - rem) != int.parse(digits[13])) return 'CNPJ inválido';
    return null;
  }

  Future<void> _pickFile(bool isDocument) async {
    final result = await FilePicker.platform.pickFiles(
      type: isDocument ? FileType.custom : FileType.image,
      allowedExtensions: isDocument ? ['pdf'] : null,
      withData: true,
    );
    if (result != null) {
      setState(() {
        if (isDocument) {
          _pickedDocumentFile = result.files.first;
        } else {
          _pickedPhotoIdFile = result.files.first;
        }
      });
    }
  }

  Future<void> _createDocument() async {
    if (_pickedDocumentFile == null || _pickedPhotoIdFile == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text('Por favor, anexe o PDF e a foto de identificação.'),
      ));
      return;
    }

    if (!_formKey.currentState!.validate()) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: Colors.orange,
        content: Text('Corrija os campos destacados antes de continuar.'),
        duration: Duration(seconds: 3),
      ));
      return;
    }

    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final token = authProvider.token;
    final companyId = authProvider.companyId;

    if (token == null || companyId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text('Erro de autenticação. Faça login novamente.'),
      ));
      return;
    }

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    final navigator = Navigator.of(context);
    final scaffoldMessenger = ScaffoldMessenger.of(context);

    final error = await _documentRepository.createDocumentWithFiles(
      companyId: companyId,
      statusId: 2,
      documentFileName: _pickedDocumentFile!.name,
      documentFileBytes: _pickedDocumentFile!.bytes!,
      signerFullName: _signerFullNameController.text.trim(),
      signerPhoneNumber: _signerPhoneNumberController.text.trim(),
      signerEmail: _signerEmailController.text.trim(),
      signerNationalId: _signerNationalIdController.text.replaceAll(RegExp(r'\D'), ''),
      photoIdFileName: _pickedPhotoIdFile!.name,
      photoIdFileBytes: _pickedPhotoIdFile!.bytes!,
    );

    navigator.pop(); 

    if (error == null) {
      scaffoldMessenger.showSnackBar(const SnackBar(
        backgroundColor: Colors.green,
        content: Text('Documento enviado com sucesso!'),
      ));
      navigator.pop();
    } else {
      final msg = _friendlyBackendError(error);
      scaffoldMessenger.showSnackBar(SnackBar(
        backgroundColor: Colors.redAccent,
        content: Text(msg),
        duration: const Duration(seconds: 4),
      ));
    }
  }

  String _friendlyBackendError(String raw) {
    final lower = raw.toLowerCase();
    if (lower.contains('email') &&
        (lower.contains('já') || lower.contains('duplicado') || lower.contains('existe'))) {
      return 'E-mail do signatário já cadastrado no sistema.';
    }
    if (lower.contains('cpf') || lower.contains('national_id')) {
      return 'CPF do signatário inválido ou já cadastrado.';
    }
    if (lower.contains('cnpj')) {
      return 'CNPJ inválido ou já cadastrado.';
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
              _buildFileUploadWidget(isDocument: true),

              const SizedBox(height: 32),

              _sectionTitle('2. Dados do Signatário'),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _signerFullNameController,
                label: 'Nome Completo',
                validator: _validateRequired,
              ),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _signerNationalIdController,
                label: 'CPF / CNPJ',
                hint: '000.000.000-00 ou 00.000.000/0001-00',
                keyboardType: TextInputType.number,
                validator: _validateCpfOrCnpj,
              ),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _signerPhoneNumberController,
                label: 'Telefone (com DDD)',
                hint: '85999999999',
                keyboardType: TextInputType.phone,
                validator: _validatePhone,
              ),
              const SizedBox(height: 16),
              _buildTextField(
                controller: _signerEmailController,
                label: 'E-mail do Signatário',
                keyboardType: TextInputType.emailAddress,
                validator: _validateEmail,
              ),

              const SizedBox(height: 32),

              _sectionTitle('3. Foto de Identificação (ID)'),
              const SizedBox(height: 16),
              _buildFileUploadWidget(isDocument: false),

              const SizedBox(height: 40),
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

  Widget _buildFileUploadWidget({required bool isDocument}) {
    final file = isDocument ? _pickedDocumentFile : _pickedPhotoIdFile;
    final title = isDocument ? 'Selecionar Arquivo PDF' : 'Selecionar Foto (ID)';

    if (file != null) {
      return Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.textFieldFill,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.textFieldBorder),
        ),
        child: Row(
          children: [
            Icon(
              isDocument ? Icons.picture_as_pdf : Icons.image,
              color: isDocument ? Colors.red : AppColors.primaryButton,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(file.name,
                  style: GoogleFonts.poppins(), overflow: TextOverflow.ellipsis),
            ),
            IconButton(
              icon: const Icon(Icons.close, size: 20),
              onPressed: () => setState(() {
                if (isDocument) {
                  _pickedDocumentFile = null;
                } else {
                  _pickedPhotoIdFile = null;
                }
              }),
            ),
          ],
        ),
      );
    }

    return OutlinedButton.icon(
      icon: const Icon(Icons.upload_file_outlined),
      label: Text(title),
      onPressed: () => _pickFile(isDocument),
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.primaryButton,
        minimumSize: const Size(double.infinity, 50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        side: const BorderSide(color: AppColors.primaryButton),
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
