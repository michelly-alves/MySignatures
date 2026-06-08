import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';
import '../../data/models/document_model.dart';
import '../../data/repositories/document_signer_repository.dart';
import '../../data/repositories/document_repository.dart';
import '../../theme/app_colors.dart';
import '../providers/auth_provider.dart';
import '../widgets/document_status_badge.dart';
import 'documents/document_list_screen.dart';
import 'documents/create_document_screen.dart';
import 'documents/document_sign_screen.dart';
import 'documents/facial_recognition_screen.dart';
import 'documents/pending_documents_screen.dart';
import 'profile/settings_screen.dart';
import 'public/signature_validation_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Future<List<Document>>? _recentDocumentsFuture;
  String? _loadedToken;

  Future<List<Document>> _loadRecentDocuments(String token) {
    if (_recentDocumentsFuture == null || _loadedToken != token) {
      _loadedToken = token;
      _recentDocumentsFuture = DocumentRepository().getDocuments(token: token);
    }
    return _recentDocumentsFuture!;
  }

  void _retryRecentDocuments() {
    setState(() {
      _recentDocumentsFuture = null;
      _loadedToken = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = Provider.of<AuthProvider>(context);

    if (!auth.isAuthCheckComplete) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (!auth.isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.pushReplacementNamed(context, '/login');
      });
      return const Scaffold();
    }

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(
          'E-Signature',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.bold,
          ),
        ),
        actions: [
          IconButton(
            tooltip: 'Validar assinatura',
            icon: const Icon(
              Icons.verified_outlined,
              color: AppColors.primaryText,
              size: 26,
            ),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => const SignatureValidationScreen(),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Minha conta',
            icon: const Icon(
              Icons.account_circle_outlined,
              color: AppColors.primaryText,
              size: 28,
            ),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              );
            },
          ),
          const SizedBox(width: 10),
        ],
      ),
      body: Consumer<AuthProvider>(
        builder: (context, auth, child) {
          final token = auth.token;
          final userName = auth.user?['legal_name'] ??
              auth.user?['full_name'] ??
              auth.user?['name'] ??
              'Usuário';
          final role = auth.user?['role'];

          return SingleChildScrollView(
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildWelcomeHeader(userName),
                  const SizedBox(height: 32),
                  _buildQuickActions(context, token, role),
                  const SizedBox(height: 40),
                  _buildRecentDocumentsSection(context, token, role),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _openDocumentFromHome(
    BuildContext context,
    Document doc,
    String? token,
    int? role,
  ) async {
    if (role == 2 && doc.statusId != 3) {
      final auth = Provider.of<AuthProvider>(context, listen: false);
      final userId = auth.userId;
      final messenger = ScaffoldMessenger.of(context);
      final navigator = Navigator.of(context);

      if (userId == null) {
        messenger.showSnackBar(
          const SnackBar(
            content: Text('Usuário não identificado. Faça login novamente.'),
          ),
        );
        return;
      }

      final signers = await DocumentSignerRepository().getDocumentSigners(
        documentId: doc.documentId,
      );

      if (!mounted) return;

      final signer = signers.isNotEmpty ? signers.first : null;

      if (signer == null || signer.statusId != 2) {
        final verified = await navigator.push<bool>(
          MaterialPageRoute(
            builder: (_) => FacialRecognitionScreen(
              userId: userId.toString(),
              documentId: doc.documentId,
            ),
          ),
        );

        if (!mounted) return;
        if (verified != true) return;
      }

      await navigator.push(
        MaterialPageRoute(builder: (_) => DocumentSignScreen(document: doc)),
      );
      // Atualiza documentos recentes ao voltar da tela de assinatura
      if (mounted) _retryRecentDocuments();
      return;
    }

    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DocumentSignScreen(document: doc, allowSigning: false),
      ),
    );
  }

  Widget _buildRecentDocumentsSection(
    BuildContext context,
    String? token,
    int? role,
  ) {
    if (token == null) return const SizedBox.shrink();

    return FutureBuilder<List<Document>>(
      future: _loadRecentDocuments(token),
      builder: (context, snapshot) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Últimos Documentos',
              style: GoogleFonts.poppins(
                fontSize: 22,
                fontWeight: FontWeight.bold,
                color: AppColors.primaryText,
              ),
            ),
            const SizedBox(height: 16),
            if (snapshot.connectionState == ConnectionState.waiting)
              const Center(child: CircularProgressIndicator())
            else if (snapshot.hasError)
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Não foi possível carregar seus documentos.',
                    style: GoogleFonts.poppins(
                      color: Colors.red.shade700,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: _retryRecentDocuments,
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Tentar novamente'),
                    style: TextButton.styleFrom(
                      foregroundColor: AppColors.primaryButton,
                      padding: EdgeInsets.zero,
                    ),
                  ),
                ],
              )
            else if (!snapshot.hasData || snapshot.data!.isEmpty)
              Text(
                'Nenhum documento vinculado a você ainda.',
                style: GoogleFonts.poppins(
                  color: AppColors.primaryText.withValues(alpha: 0.7),
                  fontSize: 14,
                ),
              )
            else
              ...([...snapshot.data!]
                    ..sort((a, b) => b.createdAt.compareTo(a.createdAt)))
                  .take(5)
                  .map(
                    (doc) => _buildRecentDocumentItem(
                      context: context,
                      doc: doc,
                      token: token,
                      role: role,
                    ),
                  ),
          ],
        );
      },
    );
  }

  Widget _buildRecentDocumentItem({
    required BuildContext context,
    required Document doc,
    required String? token,
    required int? role,
  }) {
    // ← usa DocumentStatus do widget compartilhado, sem duplicação
    final status = DocumentStatus.of(doc.statusId);

    return InkWell(
      onTap: () async => _openDocumentFromHome(context, doc, token, role),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.textFieldFill,
          borderRadius: BorderRadius.circular(12),
          border: Border(left: BorderSide(color: status.color, width: 4)),
        ),
        child: Row(
          children: [
            Icon(status.icon, color: status.color, size: 32),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    doc.fileName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: GoogleFonts.poppins(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primaryText,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${status.label} • ${DateFormat("dd/MM/yyyy 'às' HH:mm").format(doc.createdAt)}',
                    style: GoogleFonts.poppins(
                      fontSize: 13,
                      color: AppColors.primaryText.withValues(alpha: 0.7),
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.arrow_forward_ios, size: 16, color: Colors.grey),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context, String? token, int? role) {
    final isCompany = role == 0;
    final isSigner = role == 2;

    final actions = [
      if (isCompany)
        _buildActionCard(
          icon: Icons.add_to_drive_outlined,
          label: 'Criar Documento',
          onTap: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const CreateDocumentScreen()),
            );
          },
        ),
      _buildActionCard(
        icon: Icons.folder_open_outlined,
        label: 'Meus Documentos',
        onTap: () {
          if (token != null) {
            Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => DocumentsListScreen(token: token),
              ),
            );
          } else {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Token ainda não disponível. Aguarde.')),
            );
          }
        },
      ),
      if (isSigner)
        _buildActionCard(
          icon: Icons.edit_outlined,
          label: 'Assinaturas Pendentes',
          onTap: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const PendingDocumentsScreen()),
            );
          },
        ),
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: 220,
        childAspectRatio: 1.1,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
      ),
      itemCount: actions.length,
      itemBuilder: (context, index) => actions[index],
    );
  }

  Widget _buildActionCard({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.textFieldFill,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 36, color: AppColors.primaryButton),
            const SizedBox(height: 12),
            Text(
              label,
              textAlign: TextAlign.center,
              style: GoogleFonts.poppins(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                color: AppColors.primaryText,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWelcomeHeader(String userName) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Bem-vindo(a) de volta,',
          style: GoogleFonts.poppins(
            fontSize: 22,
            color: AppColors.primaryText.withValues(alpha: 0.7),
          ),
        ),
        Text(
          userName,
          style: GoogleFonts.poppins(
            fontSize: 36,
            fontWeight: FontWeight.bold,
            color: AppColors.primaryText,
          ),
        ),
      ],
    );
  }
}
