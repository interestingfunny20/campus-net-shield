"""
检测报告导出模块

把一次检测结果导出为 txt 或 PDF，便于留存与复核。
PDF 中文用 reportlab 内置 CID 字体（STSong-Light），无需外部字体文件，解决乱码。
"""
import datetime
import os


class ReportExporter:

    @staticmethod
    def to_text(report):
        """把检测报告格式化为可读的纯文本"""
        lines = []
        lines.append("========================================================")
        lines.append("  校园钓鱼网页检测助手 —— 检测报告")
        lines.append("========================================================")
        lines.append(f'检测时间     : {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        lines.append(f'检测网址     : {report.get("url", "")}')
        lines.append(f'检测耗时     : {report.get("elapsed", 0)} 秒')
        lines.append("--------------------------------------------------------")
        level = report.get("level", "")
        lines.append(f'【风险等级】: {level}（风险分 {report.get("score", 0)} / 100）')
        fetch = report.get("fetch", {})
        lines.append("--------------------------------------------------------")
        lines.append("【页面抓取情况】")
        if fetch.get("ok"):
            lines.append(f'  抓取状态   : 成功（HTTP {fetch.get("status", "?")}）')
            lines.append(f'  页面标题   : {fetch.get("title", "（无标题）")}')
            lines.append(f'  最终地址   : {fetch.get("final_url", "")}')
            lines.append(f'  重定向次数 : {fetch.get("redirect_count", 0)}')
            lines.append(f'  传输协议   : {"HTTPS（加密）" if fetch.get("is_https") else "HTTP（明文，存在被篡改风险）"}')
            lines.append(f'  表单输入框 : {fetch.get("form_count", 0)} 个')
        else:
            lines.append(f'  抓取失败   : {fetch.get("error", "未知原因")}（已按域名特征完成基础检测）')
        lines.append("--------------------------------------------------------")
        lines.append("【风险原因】")
        if report.get("reasons"):
            for i, r in enumerate(report["reasons"], 1):
                lines.append(f"  {i}. {r}")

        else:
            lines.append("  未发现明显风险特征。")
        lines.append("--------------------------------------------------------")
        lines.append("【检测结论】")
        lines.append(f'  {report.get("conclusion", "")}')
        lines.append("--------------------------------------------------------")
        lines.append("【安全提示】")
        lines.append("  1. 本工具为辅助识别工具，不能保证100%识别所有钓鱼网站；")
        lines.append("  2. 高校不会通过网页直接索要银行卡号、验证码，遇到请立即停止操作；")
        lines.append("  3. 涉及转账、缴费、领奖的操作，务必通过学校官网公布的官方渠道核实；")
        lines.append("  4. 如已输入个人信息，请尽快修改相关密码并联系学校网络与信息安全部门。")
        lines.append("========================================================")
        lines.append("  生成工具：校园钓鱼网页检测助手（学生课外科研作品，非商业软件）")
        return "\n".join(lines)

    @staticmethod
    def to_pdf(report, path):
        """
        把检测报告导出为 PDF（中文正常显示）。
        使用 reportlab 内置 CID 字体 STSong-Light，无需外部字体文件。
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        CN_FONT = "STSong-Light"
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("CNTitle",
          parent=(styles["Title"]), fontName=CN_FONT, fontSize=18,
          leading=24,
          textColor=(colors.HexColor("#7c3aed")),
          spaceAfter=6)
        h2_style = ParagraphStyle("CNH2",
          parent=(styles["Heading2"]), fontName=CN_FONT, fontSize=12,
          leading=16,
          textColor=(colors.HexColor("#ec4899")),
          spaceBefore=10,
          spaceAfter=4)
        body_style = ParagraphStyle("CNBody",
          parent=(styles["Normal"]), fontName=CN_FONT, fontSize=10,
          leading=15,
          textColor=(colors.HexColor("#333333")))
        small_style = ParagraphStyle("CNSmall",
          parent=(styles["Normal"]), fontName=CN_FONT, fontSize=8,
          leading=12,
          textColor=(colors.HexColor("#999999")))
        level = report.get("level", "—")
        score = report.get("score", 0)
        level_color = {
          '安全': "#16a34a", '可疑': "#f59e0b", '高危': "#dc2626", '未知': "#9ca3af"}.get(level, "#666666")
        doc = SimpleDocTemplate(path,
          pagesize=A4, leftMargin=(20 * mm),
          rightMargin=(20 * mm),
          topMargin=(18 * mm),
          bottomMargin=(18 * mm))
        story = []
        story.append(Paragraph("校园钓鱼网页检测报告", title_style))
        story.append(Paragraph("闽南科技学院 · 网络工程专业 · 挑战杯参赛作品", small_style))
        story.append(Spacer(1, 8))
        info_data = [
         [
          "检测时间", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
         [
          "检测网址", report.get("url", "")],
         [
          "检测耗时", f'{report.get("elapsed", 0)} 秒'],
         [
          "风险等级", f"<b>{level}</b>（{score} / 100）"]]
        info_table = Table([[Paragraph(c, body_style) for c in row] for row in info_data],
          colWidths=[
         35 * mm, 130 * mm])
        info_table.setStyle(TableStyle([
         (
          "FONTNAME", (0, 0), (-1, -1), CN_FONT),
         ('FONTSIZE', (0, 0), (-1, -1), 10),
         (
          "BACKGROUND", (0, 0), (0, -1), colors.HexColor("#faf5ff")),
         (
          "TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#7c3aed")),
         (
          "GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e9d5ff")),
         ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
         ('LEFTPADDING', (0, 0), (-1, -1), 8),
         ('TOPPADDING', (0, 0), (-1, -1), 6),
         ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(info_table)
        story.append(Spacer(1, 10))
        story.append(Paragraph("一、检测结论", h2_style))
        conclusion_style = ParagraphStyle("Conclusion",
          parent=body_style, fontSize=11, leading=16, textColor=(colors.HexColor(level_color)))
        story.append(Paragraph(report.get("conclusion", ""), conclusion_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph("二、风险原因详情", h2_style))
        reasons = report.get("reasons", [])
        if reasons:
            for (i, r) in enumerate(reasons, 1):
                story.append(Paragraph(f"{i}. {r}", body_style))

        else:
            story.append(Paragraph("未发现明显风险特征。", body_style))
        story.append(Spacer(1, 6))
        story.append(Paragraph("三、页面抓取情况", h2_style))
        fetch = report.get("fetch", {})
        if fetch.get("ok"):
            fetch_data = [["抓取状态", f'成功（HTTP {fetch.get("status", "?")}）'],
             [
              "页面标题", fetch.get("title", "（无标题）")],
             [
              "最终地址", fetch.get("final_url", "")],
             [
              "重定向次数", f'{fetch.get("redirect_count", 0)} 次'],
             [
              "传输协议", "HTTPS（加密）" if fetch.get("is_https") else "HTTP（明文）"],
             [
              "表单输入框", f'{fetch.get("form_count", 0)} 个']]
        else:
            fetch_data = [["抓取状态", f'失败：{fetch.get("error", "未知原因")}'],
             [
              "说明", "已按域名特征完成基础检测"]]
        fetch_table = Table([[Paragraph(c, body_style) for c in row] for row in fetch_data],
          colWidths=[
         35 * mm, 130 * mm])
        fetch_table.setStyle(TableStyle([
         (
          "FONTNAME", (0, 0), (-1, -1), CN_FONT),
         ('FONTSIZE', (0, 0), (-1, -1), 9),
         (
          "BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fdf4ff")),
         (
          "TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#ec4899")),
         (
          "GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#fce7f3")),
         ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
         ('LEFTPADDING', (0, 0), (-1, -1), 8),
         ('TOPPADDING', (0, 0), (-1, -1), 4),
         ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        story.append(fetch_table)
        story.append(Spacer(1, 10))
        story.append(Paragraph("四、安全提示", h2_style))
        tips = [
         "1. 本工具为辅助识别工具，不能保证 100% 识别所有钓鱼网站；",
         "2. 高校不会通过网页直接索要银行卡号、验证码，遇到请立即停止操作；",
         "3. 涉及转账、缴费、领奖的操作，务必通过学校官网公布的官方渠道核实；",
         "4. 如已输入个人信息，请尽快修改相关密码并联系学校网络与信息安全部门。"]
        for t in tips:
            story.append(Paragraph(t, body_style))

        story.append(Spacer(1, 14))
        story.append(Paragraph("— 本报告由「校园钓鱼网页检测助手」自动生成 · 闽南科技学院网络工程专业 —", small_style))
        doc.build(story)
        return path

    @staticmethod
    def save(report, path=None):
        """保存报告到指定路径；未指定时存到数据根目录的 reports 目录"""
        if not path:
            home = os.environ.get("PHISHING_GUARD_HOME")
            if home:
                base = os.path.join(home, "reports")
            else:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
            os.makedirs(base, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(base, f"检测报告_{stamp}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(ReportExporter.to_text(report))
        return path
