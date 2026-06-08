class DocumentSignatureSummary {
  final int documentId;
  final int signatureId;
  final int signerId;
  final String signerName;
  final DateTime? signedAt;
  final String? validationCode;
  final String? validationUrl;

  const DocumentSignatureSummary({
    required this.documentId,
    required this.signatureId,
    required this.signerId,
    required this.signerName,
    this.signedAt,
    this.validationCode,
    this.validationUrl,
  });

  factory DocumentSignatureSummary.fromJson(Map<String, dynamic> json) {
    return DocumentSignatureSummary(
      documentId: json['document_id'],
      signatureId: json['signature_id'],
      signerId: json['signer_id'],
      signerName: json['signer_name'] ?? 'Signatário',
      signedAt: json['signed_at'] != null
          ? DateTime.parse(json['signed_at'])
          : null,
      validationCode: json['validation_code'],
      validationUrl: json['validation_url'],
    );
  }
}
