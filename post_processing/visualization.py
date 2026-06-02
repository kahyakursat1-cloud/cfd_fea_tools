"""
Visualization Module — Matplotlib ile sonuçları çiz

Yapılandırma:
- CFD: Convergence, Pressure, Velocity, Streamlines
- FEA: Stress, Deformation, Modal shapes
"""

import io

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure


class CFDVisualizer:
    """CFD sonuçlarını görselleştir"""

    @staticmethod
    def plot_convergence_history(iterations: np.ndarray,
                                 pressure_residuals: np.ndarray,
                                 velocity_residuals: np.ndarray,
                                 drag_history: np.ndarray | None = None) -> Figure:
        """Convergence history grafiği (residuals + forces)"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

        # Residuals (log scale)
        ax1.semilogy(iterations, pressure_residuals, 'b-', linewidth=2, label='Pressure')
        ax1.semilogy(iterations, velocity_residuals, 'r-', linewidth=2, label='Velocity')
        ax1.set_xlabel('Iteration', fontsize=11)
        ax1.set_ylabel('Residual (log scale)', fontsize=11)
        ax1.set_title('Convergence History — Residuals', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='upper right')

        # Drag force (if available)
        if drag_history is not None:
            ax2.plot(iterations, drag_history, 'g-', linewidth=2.5)
            ax2.set_xlabel('Iteration', fontsize=11)
            ax2.set_ylabel('Drag Force (N)', fontsize=11)
            ax2.set_title('Convergence History — Drag Force', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3)

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_pressure_contours(x: np.ndarray, y: np.ndarray,
                               pressure: np.ndarray) -> Figure:
        """Basınç dağılımı (contour plot)"""
        fig, ax = plt.subplots(figsize=(10, 8))

        # Create contour plot
        contour = ax.tricontourf(x, y, pressure, levels=20, cmap='RdYlBu_r')
        contour_lines = ax.tricontour(x, y, pressure, levels=10, colors='k',
                                      linewidths=0.5, alpha=0.3)
        ax.clabel(contour_lines, inline=True, fontsize=8)

        cbar = plt.colorbar(contour, ax=ax, label='Pressure (Pa)')
        ax.set_xlabel('X (m)', fontsize=11)
        ax.set_ylabel('Y (m)', fontsize=11)
        ax.set_title('Pressure Distribution — CFD Analysis', fontsize=12, fontweight='bold')

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_velocity_magnitude(x: np.ndarray, y: np.ndarray,
                                u: np.ndarray, v: np.ndarray) -> Figure:
        """Hız büyüklüğü (magnitude contours)"""
        fig, ax = plt.subplots(figsize=(10, 8))

        velocity_mag = np.sqrt(u**2 + v**2)

        contour = ax.tricontourf(x, y, velocity_mag, levels=20, cmap='viridis')
        cbar = plt.colorbar(contour, ax=ax, label='Velocity (m/s)')

        ax.set_xlabel('X (m)', fontsize=11)
        ax.set_ylabel('Y (m)', fontsize=11)
        ax.set_title('Velocity Magnitude — CFD Analysis', fontsize=12, fontweight='bold')

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_streamlines(x: np.ndarray, y: np.ndarray,
                         u: np.ndarray, v: np.ndarray,
                         pressure: np.ndarray | None = None) -> Figure:
        """Akış çizgileri (streamlines)"""
        fig, ax = plt.subplots(figsize=(11, 8))

        # Background: pressure if available
        if pressure is not None:
            contourf = ax.tricontourf(x, y, pressure, levels=15, cmap='RdYlBu_r', alpha=0.7)
            plt.colorbar(contourf, ax=ax, label='Pressure (Pa)')

        # Streamlines
        ax.quiver(x, y, u, v, alpha=0.6, scale=50)

        ax.set_xlabel('X (m)', fontsize=11)
        ax.set_ylabel('Y (m)', fontsize=11)
        ax.set_title('Flow Field — Streamlines & Velocity Vectors', fontsize=12, fontweight='bold')
        ax.set_aspect('equal')

        fig.tight_layout()
        return fig


class FEAVisualizer:
    """FEA sonuçlarını görselleştir"""

    @staticmethod
    def plot_stress_distribution(x: np.ndarray, y: np.ndarray,
                                stress: np.ndarray,
                                material_yield: float = 275.0) -> Figure:
        """Von Mises stress dağılımı"""
        fig, ax = plt.subplots(figsize=(10, 8))

        # Stress distribution
        contour = ax.tricontourf(x, y, stress, levels=20, cmap='YlOrRd')
        cbar = plt.colorbar(contour, ax=ax, label='Von Mises Stress (MPa)')

        # Yield line
        ax.contour(x, y, stress, levels=[material_yield], colors='black',
                   linewidths=2, linestyles='--')

        ax.set_xlabel('X (m)', fontsize=11)
        ax.set_ylabel('Y (m)', fontsize=11)
        ax.set_title(f'Von Mises Stress Distribution (Yield: {material_yield} MPa)',
                     fontsize=12, fontweight='bold')

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_deformation(original_coords: np.ndarray,
                        deformed_coords: np.ndarray,
                        scale: float = 10.0) -> Figure:
        """Deformasyon (original vs deformed)"""
        fig, ax = plt.subplots(figsize=(10, 8))

        # Original geometry (dashed)
        ax.plot(original_coords[:, 0], original_coords[:, 1], 'b--',
                linewidth=1.5, alpha=0.5, label='Original')

        # Deformed geometry
        ax.plot(deformed_coords[:, 0], deformed_coords[:, 1], 'r-',
                linewidth=2, label=f'Deformed (×{scale} scale)')

        # Displacement vectors
        displacement = deformed_coords - original_coords
        ax.quiver(original_coords[:, 0], original_coords[:, 1],
                  displacement[:, 0] * scale, displacement[:, 1] * scale,
                  alpha=0.3, scale=1, scale_units='xy')

        ax.set_xlabel('X (m)', fontsize=11)
        ax.set_ylabel('Y (m)', fontsize=11)
        ax.set_title('Structural Deformation (Amplified)', fontsize=12, fontweight='bold')
        ax.legend(loc='best')
        ax.axis('equal')

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_modal_frequencies(frequencies: list[float],
                               mode_numbers: list[int] | None = None) -> Figure:
        """Modal frekansları bar grafik"""
        fig, ax = plt.subplots(figsize=(10, 6))

        if mode_numbers is None:
            mode_numbers = list(range(1, len(frequencies) + 1))

        colors = plt.cm.viridis(np.linspace(0, 1, len(frequencies)))
        ax.bar(mode_numbers[:10], frequencies[:10], color=colors[:10], alpha=0.8)

        ax.set_xlabel('Mode Number', fontsize=11)
        ax.set_ylabel('Frequency (Hz)', fontsize=11)
        ax.set_title('Natural Frequencies (First 10 Modes)', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')

        # Add value labels on bars
        for i, (mode, freq) in enumerate(zip(mode_numbers[:10], frequencies[:10])):
            ax.text(mode, freq + 1, f'{freq:.1f}', ha='center', fontsize=9)

        fig.tight_layout()
        return fig

    @staticmethod
    def plot_stress_vs_load(loads: np.ndarray, stresses: np.ndarray,
                           material_yield: float = 275.0) -> Figure:
        """Yük vs gerilme eğrisi"""
        fig, ax = plt.subplots(figsize=(10, 6))

        ax.plot(loads, stresses, 'b-', linewidth=2.5, marker='o', markersize=6, label='Analysis')
        ax.axhline(y=material_yield, color='r', linestyle='--', linewidth=2, label=f'Yield ({material_yield} MPa)')

        ax.fill_between(loads, 0, stresses, alpha=0.2)

        ax.set_xlabel('Applied Load (Pa)', fontsize=11)
        ax.set_ylabel('Max Stress (MPa)', fontsize=11)
        ax.set_title('Stress vs Applied Load', fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left')

        fig.tight_layout()
        return fig


class CommonVisualizer:
    """Ortak grafikler"""

    @staticmethod
    def plot_results_table(results_dict: dict) -> Figure:
        """Sonuçları tablo şeklinde göster"""
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.axis('tight')
        ax.axis('off')

        # Prepare table data
        rows = []
        for key, value in results_dict.items():
            if isinstance(value, float):
                rows.append([key, f'{value:.4f}'])
            else:
                rows.append([key, str(value)])

        table = ax.table(cellText=rows,
                        colLabels=['Parameter', 'Value'],
                        cellLoc='left',
                        loc='center',
                        colWidths=[0.6, 0.4])

        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 2)

        # Style header
        for i in range(2):
            table[(0, i)].set_facecolor('#4CAF50')
            table[(0, i)].set_text_props(weight='bold', color='white')

        # Alternate row colors
        for i in range(1, len(rows) + 1):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#f0f0f0')

        fig.suptitle('Analysis Summary', fontsize=14, fontweight='bold', y=0.98)
        return fig

    @staticmethod
    def save_figure_to_bytes(fig: Figure) -> bytes:
        """Figure'i bytes'a dönüştür (PDF/PNG için)"""
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        return buf.getvalue()


# For testing
if __name__ == "__main__":
    # Test convergence plot
    iterations = np.array([0, 100, 200, 500, 1000, 2000])
    p_res = np.array([1e0, 1e-1, 1e-2, 1e-3, 1e-4, 1e-5])
    u_res = np.array([1e0, 5e-2, 1e-2, 5e-4, 1e-5, 1e-6])
    drag = np.array([250, 245, 242, 241, 240.5, 240.3])

    fig = CFDVisualizer.plot_convergence_history(iterations, p_res, u_res, drag)
    plt.savefig('/tmp/convergence.png', dpi=100)
    print("[OK] Convergence plot saved")

    # Test stress plot
    n = 100
    x = np.random.uniform(-1, 1, n)
    y = np.random.uniform(-1, 1, n)
    stress = 100 + 50 * np.sin(x) * np.cos(y)

    fig = FEAVisualizer.plot_stress_distribution(x, y, stress)
    plt.savefig('/tmp/stress.png', dpi=100)
    print("[OK] Stress plot saved")
