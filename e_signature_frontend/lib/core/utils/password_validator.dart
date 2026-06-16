
class PasswordValidator {

  static String? validate(String? value) {
    if (value == null || value.isEmpty) return 'Campo obrigatório';
    if (value.length < 8) return 'A senha deve ter pelo menos 8 caracteres';
    if (!RegExp(r'[A-Z]').hasMatch(value)) {
      return 'A senha deve conter pelo menos uma letra maiúscula';
    }
    if (!RegExp(r'\d').hasMatch(value)) {
      return 'A senha deve conter pelo menos um número';
    }
    if (!RegExp(r'[^A-Za-z0-9]').hasMatch(value)) {
      return 'A senha deve conter pelo menos um caractere especial';
    }
    return null;
  }
}
