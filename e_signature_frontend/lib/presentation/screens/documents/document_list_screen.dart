import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../../core/utils/brt_formatter.dart';
import '../../../data/repositories/document_repository.dart';
import '../../../data/models/document_model.dart';
import '../../../data/models/document_signature_summary_model.dart';
import '../../providers/auth_provider.dart';
import '../../../theme/app_colors.dart';
import '../../widgets/document_status_badge.dart';
import 'document_sign_screen.dart';

class DocumentsListScreen extends StatefulWidget {
  final String token;
  const DocumentsListScreen({super.key, required this.token});

  @override
  State<DocumentsListScreen> createState() => _DocumentsListScreenState();
}

class _DocumentsListScreenState extends State<DocumentsListScreen> {
  List<Document>? _documents;
  bool _isLoading = true;
  String? _errorMessage;
  final Map<int, Future<DocumentSignatureSummary?>> _signatureFutures = {};

  @override
  void initState() {
    super.initState();
    _fetchDocuments();
  }

  Future<void> _fetchDocuments() async {
    if (!mounted) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final docs = await DocumentRepository().getDocuments(token: widget.token);
      if (mounted) {
        setState(() {
          _documents = docs;
          _isLoading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Não foi possível carregar os documentos.';
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _refresh() async {
    _signatureFutures.clear();
    await _fetchDocuments();
  }

  Future<DocumentSignatureSummary?> _signatureSummaryFuture(Document doc) {
    return _signatureFutures.putIfAbsent(
      doc.documentId,
      () => DocumentRepository().getSignatureSummary(documentId: doc.documentId),
    );
  }

  void _openDocument(Document doc) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => DocumentSignScreen(document: doc, allowSigning: false),
      ),
    );
  }

  Widget _buildSignatureSummary(Document doc) {
    if (doc.statusId != 3) return const SizedBox.shrink();

    return FutureBuilder<DocumentSignatureSummary?>(
      future: _signatureSummaryFuture(doc),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Carregando assinatura...',
              style: GoogleFonts.poppins(color: Colors.grey.shade600, fontSize: 12),
            ),
          );
        }

        final summary = snapshot.data;
        if (summary == null) {
          return Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              'Assinatura registrada, detalhes indisponíveis.',
              style: GoogleFonts.poppins(color: Colors.grey.shade600, fontSize: 12),
            ),
          );
        }

        final signedAt = summary.signedAt != null
            ? formatBrt(summary.signedAt!)
            : 'data indisponível';
        final validationCode = summary.validationCode;

        return Container(
          margin: const EdgeInsets.only(top: 10),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.green.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.green.withValues(alpha: 0.22)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.verified_outlined, color: Colors.green.shade700, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Assinado por ${summary.signerName} em $signedAt',
                      style: GoogleFonts.poppins(
                        color: Colors.green.shade800,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    if (validationCode != null && validationCode.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          'Validação pública: $validationCode',
                          style: GoogleFonts.poppins(
                            color: Colors.green.shade700,
                            fontSize: 11,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildLoadingState() {
    return const Center(child: CircularProgressIndicator());
  }

  Widget _buildErrorState() {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 56, color: Colors.redAccent),
                  const SizedBox(height: 16),
                  Text(
                    _errorMessage!,
                    textAlign: TextAlign.center,
                    style: GoogleFonts.poppins(
                      color: AppColors.primaryText,
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 20),
                  ElevatedButton.icon(
                    onPressed: _fetchDocuments,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Tentar novamente'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primaryButton,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
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

  Widget _buildEmptyState() {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Text(
              'Nenhum documento encontrado.',
              style: GoogleFonts.poppins(color: AppColors.primaryText),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildList(List<Document> documents) {
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: documents.length,
      itemBuilder: (context, index) {
        final doc = documents[index];
        return Card(
          elevation: 2,
          margin: const EdgeInsets.only(bottom: 16),
          color: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: InkWell(
            onTap: () => _openDocument(doc),
            borderRadius: BorderRadius.circular(12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        Icons.description_outlined,
                        color: Theme.of(context).primaryColor,
                        size: 40,
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              doc.fileName,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: GoogleFonts.poppins(
                                color: AppColors.primaryText,
                                fontWeight: FontWeight.w600,
                                fontSize: 16,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              formatBrt(doc.createdAt),
                              style: GoogleFonts.poppins(
                                color: Colors.grey.shade600,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 16),
                      // ← widget compartilhado, sem duplicação
                      DocumentStatusBadge(statusId: doc.statusId),
                      const SizedBox(width: 8),
                      Icon(Icons.visibility_outlined, color: Colors.grey.shade600, size: 20),
                    ],
                  ),
                  _buildSignatureSummary(doc),
                ],
              ),
            ),
          ),
        );
      },
    );
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
          'Meus Documentos',
          style: GoogleFonts.poppins(
            color: AppColors.primaryText,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      body: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          if (!auth.isAuthCheckComplete) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!auth.isAuthenticated) {
            return const Center(
              child: Text('Erro de autenticação. Faça o login novamente.'),
            );
          }

          return RefreshIndicator(
            onRefresh: _refresh,
            child: _isLoading
                ? _buildLoadingState()
                : _errorMessage != null
                    ? _buildErrorState()
                    : (_documents?.isEmpty ?? true)
                        ? _buildEmptyState()
                        : _buildList(_documents!),
          );
        },
      ),
    );
  }
}
