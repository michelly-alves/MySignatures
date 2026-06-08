import 'dart:convert';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:typed_data';

@JS('crypto')
external JSObject get _crypto;

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
  JSObject get _subtle => _crypto['subtle'] as JSObject;

  Future<KeySetupResult> generateAndEncryptKeyPair(String password) async {
    final rsaAlgo = JSObject();
    rsaAlgo['name'] = 'RSA-PSS'.toJS;
    rsaAlgo['modulusLength'] = 2048.toJS;
    rsaAlgo['publicExponent'] = Uint8List.fromList([1, 0, 1]).toJS;
    rsaAlgo['hash'] = 'SHA-256'.toJS;

    final keyPair = await _subtle
        .callMethod<JSPromise<JSObject>>(
          'generateKey'.toJS, rsaAlgo, true.toJS, ['sign', 'verify'].jsify())
        .toDart;

    final privateKey = keyPair['privateKey'] as JSObject;
    final publicKey  = keyPair['publicKey']  as JSObject;


    final pubBuffer = await _subtle
        .callMethod<JSPromise<JSArrayBuffer>>(
            'exportKey'.toJS, 'spki'.toJS, publicKey)
        .toDart;
    final pubBytes = Uint8List.view(pubBuffer.toDart);

    final privBuffer = await _subtle
        .callMethod<JSPromise<JSArrayBuffer>>(
            'exportKey'.toJS, 'pkcs8'.toJS, privateKey)
        .toDart;
    final privBytes = Uint8List.view(privBuffer.toDart);

    final saltJs = Uint8List(32).toJS;
    _crypto.callMethod('getRandomValues'.toJS, saltJs);
    final salt = saltJs.toDart;

    final ivJs = Uint8List(12).toJS;
    _crypto.callMethod('getRandomValues'.toJS, ivJs);
    final iv = ivJs.toDart;

    final aesKey = await _deriveAesKey(password, salt, ['encrypt']);

    final encParams = JSObject();
    encParams['name'] = 'AES-GCM'.toJS;
    encParams['iv'] = iv.toJS;

    final ciphertextBuffer = await _subtle
        .callMethod<JSPromise<JSArrayBuffer>>(
          'encrypt'.toJS, encParams, aesKey, privBytes.toJS)
        .toDart;
    final ciphertext = Uint8List.view(ciphertextBuffer.toDart);

    final fileBytes = utf8.encode(jsonEncode({
      'version': 1,
      'algorithm': 'RSA-PSS-2048',
      'publicKey': base64Encode(pubBytes),
      'salt': base64Encode(salt),
      'iv': base64Encode(iv),
      'ciphertext': base64Encode(ciphertext),
    }));

    return KeySetupResult(
      publicKeyPem: _toPem('PUBLIC KEY', pubBytes),
      encryptedKeyFile: Uint8List.fromList(fileBytes),
    );
  }

  Future<DocumentSignatureResult> signDocumentHash(
    String documentHash,
    Uint8List encryptedKeyFile,
    String password,
  ) async {
    final Map<String, dynamic> fileData;
    try {
      fileData = jsonDecode(utf8.decode(encryptedKeyFile)) as Map<String, dynamic>;
    } catch (_) {
      throw Exception('Arquivo de chave inválido ou corrompido.');
    }

    final publicKeyBytes = base64Decode(fileData['publicKey'] as String);
    final salt       = Uint8List.fromList(base64Decode(fileData['salt']       as String));
    final iv         = Uint8List.fromList(base64Decode(fileData['iv']         as String));
    final ciphertext = Uint8List.fromList(base64Decode(fileData['ciphertext'] as String));

    final aesKey = await _deriveAesKey(password, salt, ['decrypt']);

    final decParams = JSObject();
    decParams['name'] = 'AES-GCM'.toJS;
    decParams['iv'] = iv.toJS;

    final JSArrayBuffer privBuffer;
    try {
      privBuffer = await _subtle
          .callMethod<JSPromise<JSArrayBuffer>>(
            'decrypt'.toJS, decParams, aesKey, ciphertext.toJS)
          .toDart;
    } catch (_) {
      throw Exception('Senha incorreta ou arquivo de chave corrompido.');
    }

    final rsaImportAlgo = JSObject();
    rsaImportAlgo['name'] = 'RSA-PSS'.toJS;
    rsaImportAlgo['hash'] = 'SHA-256'.toJS;

    final privateKey = await _subtle
        .callMethodVarArgs<JSPromise<JSObject>>(
          'importKey'.toJS,
          ['pkcs8'.toJS, privBuffer, rsaImportAlgo, false.toJS, ['sign'].jsify()],
        )
        .toDart;

    final signAlgo = JSObject();
    signAlgo['name'] = 'RSA-PSS'.toJS;
    signAlgo['saltLength'] = 32.toJS;

    final sigBuffer = await _subtle
        .callMethod<JSPromise<JSArrayBuffer>>(
          'sign'.toJS,
          signAlgo,
          privateKey,
          Uint8List.fromList(utf8.encode(documentHash)).toJS,
        )
        .toDart;

    return DocumentSignatureResult(
      signatureBase64: base64Encode(Uint8List.view(sigBuffer.toDart)),
      publicKeyPem: _toPem('PUBLIC KEY', publicKeyBytes),
    );
  }

  Future<JSObject> _deriveAesKey(
    String password,
    Uint8List salt,
    List<String> usages,
  ) async {
    final passKey = await _subtle
        .callMethodVarArgs<JSPromise<JSObject>>(
          'importKey'.toJS,
          [
            'raw'.toJS,
            Uint8List.fromList(utf8.encode(password)).toJS,
            'PBKDF2'.toJS,
            false.toJS,
            ['deriveKey'].jsify(),
          ],
        )
        .toDart;

    final pbkdf2Params = JSObject();
    pbkdf2Params['name'] = 'PBKDF2'.toJS;
    pbkdf2Params['salt'] = salt.toJS;
    pbkdf2Params['iterations'] = 100000.toJS;
    pbkdf2Params['hash'] = 'SHA-256'.toJS;

    final aesAlgo = JSObject();
    aesAlgo['name'] = 'AES-GCM'.toJS;
    aesAlgo['length'] = 256.toJS;

    return await _subtle
        .callMethodVarArgs<JSPromise<JSObject>>(
          'deriveKey'.toJS,
          [pbkdf2Params, passKey, aesAlgo, false.toJS, usages.jsify()],
        )
        .toDart;
  }

  String _toPem(String label, Uint8List bytes) {
    final body = base64Encode(bytes);
    final chunks = <String>[];
    for (var i = 0; i < body.length; i += 64) {
      chunks.add(body.substring(i, (i + 64).clamp(0, body.length)));
    }
    return '-----BEGIN $label-----\n${chunks.join('\n')}\n-----END $label-----';
  }
}
