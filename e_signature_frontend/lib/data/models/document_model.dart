class Document {
  final int documentId;
  final String fileName;
  final int statusId;
  final DateTime createdAt;
  final String? hashSha256;

  Document({
    required this.documentId,
    required this.fileName,
    required this.statusId,
    required this.createdAt,
    this.hashSha256,
  });

  factory Document.fromJson(Map<String, dynamic> json) {
    return Document(
      documentId: json['document_id'],
      fileName: json['file_name'],
      statusId: json['status_id'],
      createdAt: DateTime.parse(json['created_at']),
      hashSha256: json['hash_sha256'],
    );
  }
}
