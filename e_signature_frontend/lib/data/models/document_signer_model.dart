class DocumentSigner {
  final int documentId;
  final int signerId;
  final int statusId;
  final String? signerName;
  final String? signerEmail;
  final double? faceMatchScore;
  final DateTime? verifiedAt;

  DocumentSigner({
    required this.documentId,
    required this.signerId,
    required this.statusId,
    this.signerName,
    this.signerEmail,
    this.faceMatchScore,
    this.verifiedAt,
  });

  bool get hasSigned => statusId == 4;

  factory DocumentSigner.fromJson(Map<String, dynamic> json) {
    return DocumentSigner(
      documentId: json['document_id'],
      signerId: json['signer_id'],
      statusId: json['status_id'],
      signerName: json['signer_name'],
      signerEmail: json['signer_email'],
      faceMatchScore: json['face_match_score'] != null
          ? (json['face_match_score'] as num).toDouble()
          : null,
      verifiedAt: json['verified_at'] != null
          ? DateTime.parse(json['verified_at'])
          : null,
    );
  }
}
