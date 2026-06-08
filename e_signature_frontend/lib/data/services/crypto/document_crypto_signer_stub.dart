import 'dart:typed_data';

class KeySetupResult {
  final String publicKeyPem;
  final Uint8List encryptedKeyFile;

  const KeySetupResult({
    required this.publicKeyPem,
    required this.encryptedKeyFile,
  });
}

class DocumentSignatureResult {
  final String signatureBase64;
  final String publicKeyPem;

  const DocumentSignatureResult({
    required this.signatureBase64,
    required this.publicKeyPem,
  });
}

class DocumentCryptoSigner {
  Future<KeySetupResult> generateAndEncryptKeyPair(String password) {
    throw UnsupportedError('Assinatura RSA disponível apenas no Flutter Web.');
  }

  Future<DocumentSignatureResult> signDocumentHash(
    String documentHash,
    Uint8List encryptedKeyFile,
    String password,
  ) {
    throw UnsupportedError('Assinatura RSA disponível apenas no Flutter Web.');
  }
}
