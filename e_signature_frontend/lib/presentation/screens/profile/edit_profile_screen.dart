import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../theme/app_colors.dart';
import '../../providers/auth_provider.dart';
import '../../../data/repositories/auth_repository.dart';
import 'package:provider/provider.dart';

class EditProfileScreen extends StatefulWidget { final Map<String, dynamic> user; const EditProfileScreen({super.key, required this.user}); @override State<EditProfileScreen> createState() => _EditProfileScreenState(); }

class _EditProfileScreenState extends State<EditProfileScreen> {
  final _formKey = GlobalKey<FormState>();
  final AuthRepository _authRepository = AuthRepository();

  late TextEditingController _nameController;
  late TextEditingController _emailController;
  late TextEditingController _phoneController; 
  late TextEditingController _companyNameController;

  bool _isLoading = false;
  int? _role;

  @override
  void initState() {
    super.initState();
    final user = Provider.of<AuthProvider>(context, listen: false).user!;
    _role = user['role'];

    _nameController = TextEditingController(text: user['name'] ?? user['full_name'] ?? '');
    _emailController = TextEditingController(text: user['email'] ?? '');
    _phoneController = TextEditingController(text: user['phone_number'] ?? '');
    _companyNameController = TextEditingController(text: user['legal_name'] ?? '');
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _companyNameController.dispose();
    super.dispose();
  }

  Future<void> _saveProfile() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      final auth = Provider.of<AuthProvider>(context, listen: false);
      final user = auth.user!;
      Map<String, dynamic> updateData = {};

      if (_role == 0) {
        updateData['legal_name'] = _companyNameController.text.trim();
        updateData['email'] = _emailController.text.trim();
        updateData['phone_number'] = _phoneController.text.trim();
      } else if (_role == 2) {
        // Signer: nome, email, telefone
        updateData['name'] = _nameController.text.trim();
        updateData['contact_email'] = _emailController.text.trim();
        updateData['phone_number'] = _phoneController.text.trim();
      }

      final token = await _authRepository.getToken();
      if (token == null) throw Exception("Token inválido");

      final success = await _authRepository.updateUser(user['user_id'], updateData);

      if (success) {
        user.addAll(updateData);
        auth.notifyListeners();

        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Perfil atualizado com sucesso!")),
        );
        Navigator.pop(context);
      } else {
        throw Exception("Falha ao atualizar perfil");
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Erro ao salvar perfil: $e")),
      );
    } finally {
      setState(() => _isLoading = false);
    }
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
        title: Text(
          'Editar Perfil',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Container(
            constraints: const BoxConstraints(maxWidth: 500),
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.08),
                  blurRadius: 15,
                  offset: const Offset(0, 5),
                ),
              ],
            ),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    "Atualize seu perfil",
                    style: GoogleFonts.poppins(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: AppColors.primaryText,
                    ),
                  ),
                  const SizedBox(height: 32),

                  if (_role == 2) ...[
                    _buildTextField(
                      controller: _nameController,
                      label: "Nome",
                      icon: Icons.person_outline,
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return "Digite seu nome";
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 24),
                  ],

                  if (_role == 2 || _role == 0) ...[
                    _buildTextField(
                      controller: _phoneController,
                      label: "Telefone",
                      icon: Icons.phone,
                      keyboardType: TextInputType.phone,
                    ),
                    const SizedBox(height: 24),
                  ],

                  if (_role == 0) ...[
                    _buildTextField(
                      controller: _companyNameController,
                      label: "Nome da Empresa",
                      icon: Icons.business,
                    ),
                    const SizedBox(height: 24),
                  ],

                  _buildTextField(
                    controller: _emailController,
                    label: "Email",
                    icon: Icons.email_outlined,
                    keyboardType: TextInputType.emailAddress,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return "Digite seu email";
                      }
                      if (!RegExp(r"^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$")
                          .hasMatch(value.trim())) {
                        return "Digite um email válido";
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 40),

                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _saveProfile,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primaryButton,
                        padding: const EdgeInsets.symmetric(
                            vertical: 16, horizontal: 40),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(30)),
                        textStyle: GoogleFonts.poppins(
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      child: _isLoading
                          ? const CircularProgressIndicator(
                              color: Colors.white,
                            )
                          : const Text("Salvar Alterações"),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType,
      validator: validator,
      style: GoogleFonts.poppins(color: AppColors.primaryText),
      decoration: InputDecoration(
        prefixIcon: Icon(icon, color: AppColors.primaryButton),
        labelText: label,
        labelStyle:
            GoogleFonts.poppins(color: AppColors.primaryText.withValues(alpha: 0.7)),
        filled: true,
        fillColor: AppColors.textFieldFill,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}
