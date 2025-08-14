def calculate_totals(order, discount_percent):
    subtotal = sum(item[2] for item in order)
    gst_amount = subtotal * 0.05
    discount = (discount_percent / 100) * subtotal
    final_total = subtotal + gst_amount - discount
    return subtotal, gst_amount, discount, final_total
