import 'package:flutter/material.dart';

class DocumentStatus {
  final String label;
  final Color color;
  final IconData icon;

  const DocumentStatus._({
    required this.label,
    required this.color,
    required this.icon,
  });

  static DocumentStatus of(int statusId) {
    switch (statusId) {
      case 1:
        return DocumentStatus._(
          label: 'Criado',
          color: Colors.blueGrey.shade700,
          icon: Icons.description_outlined,
        );
      case 2:
        return DocumentStatus._(
          label: 'Em andamento',
          color: Colors.orange.shade700,
          icon: Icons.pending_outlined,
        );
      case 3:
        return DocumentStatus._(
          label: 'Assinado',
          color: Colors.green.shade700,
          icon: Icons.verified_outlined,
        );
      case 4:
        return DocumentStatus._(
          label: 'Cancelado',
          color: Colors.red.shade700,
          icon: Icons.cancel_outlined,
        );
      default:
        return DocumentStatus._(
          label: 'Desconhecido',
          color: Colors.grey.shade700,
          icon: Icons.help_outline,
        );
    }
  }
}

class DocumentStatusBadge extends StatelessWidget {
  final int statusId;

  const DocumentStatusBadge({super.key, required this.statusId});

  @override
  Widget build(BuildContext context) {
    final status = DocumentStatus.of(statusId);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        status.label,
        style: TextStyle(
          color: status.color,
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }
}
