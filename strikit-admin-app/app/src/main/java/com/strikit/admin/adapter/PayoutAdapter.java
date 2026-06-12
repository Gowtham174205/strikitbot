package com.strikit.admin.adapter;

import android.content.Context;
import android.content.res.ColorStateList;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;
import com.strikit.admin.R;
import com.strikit.admin.model.Payout;
import java.util.ArrayList;
import java.util.List;

public class PayoutAdapter extends RecyclerView.Adapter<PayoutAdapter.PayoutViewHolder> {

    public interface OnPayoutActionListener {
        void onRetryPayout(Payout payout);
    }

    private List<Payout> payoutsList = new ArrayList<>();
    private final OnPayoutActionListener listener;
    private final Context context;

    public PayoutAdapter(Context context, OnPayoutActionListener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void setPayouts(List<Payout> payouts) {
        this.payoutsList = payouts != null ? payouts : new ArrayList<>();
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public PayoutViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_payout, parent, false);
        return new PayoutViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull PayoutViewHolder holder, int position) {
        Payout payout = payoutsList.get(position);

        holder.tvPayoutTurfName.setText(payout.getTurfName());
        holder.tvPayoutId.setText("Payout #" + payout.getId());
        holder.tvOwnerShare.setText(payout.getOwnerShare());
        holder.tvTotalPaid.setText(payout.getTotalPaid());
        holder.tvPayoutUpi.setText("UPI ID: " + payout.getOwnerUpiId());

        if (payout.getRazorpayPayoutId() != null && !payout.getRazorpayPayoutId().isEmpty()) {
            holder.tvPayoutRazorpayId.setText("Razorpay Payout ID: " + payout.getRazorpayPayoutId());
            holder.tvPayoutRazorpayId.setVisibility(View.VISIBLE);
        } else {
            holder.tvPayoutRazorpayId.setVisibility(View.GONE);
        }

        String status = payout.getStatus() != null ? payout.getStatus().toUpperCase() : "PROCESSING";
        holder.badgePayoutStatus.setText(status);

        // Styling based on status
        if ("COMPLETED".equals(status)) {
            holder.badgePayoutStatus.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgePayoutStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_verified)));
            holder.tvPayoutFailureReason.setVisibility(View.GONE);
            holder.btnRetryPayout.setVisibility(View.GONE);
        } else if ("FAILED".equals(status)) {
            holder.badgePayoutStatus.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgePayoutStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_inactive)));
            
            if (payout.getFailureReason() != null && !payout.getFailureReason().isEmpty()) {
                holder.tvPayoutFailureReason.setText("Failure: " + payout.getFailureReason());
                holder.tvPayoutFailureReason.setVisibility(View.VISIBLE);
            } else {
                holder.tvPayoutFailureReason.setVisibility(View.GONE);
            }
            holder.btnRetryPayout.setVisibility(View.VISIBLE);
        } else { // PROCESSING / MANUAL_REVIEW / etc.
            holder.badgePayoutStatus.setTextColor(ContextCompat.getColor(context, R.color.text_primary));
            holder.badgePayoutStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.btn_grey)));
            holder.tvPayoutFailureReason.setVisibility(View.GONE);
            
            if ("MANUAL_REVIEW".equals(status)) {
                holder.btnRetryPayout.setVisibility(View.VISIBLE);
            } else {
                holder.btnRetryPayout.setVisibility(View.GONE);
            }
        }

        holder.btnRetryPayout.setOnClickListener(v -> {
            if (listener != null) {
                listener.onRetryPayout(payout);
            }
        });
    }

    @Override
    public int getItemCount() {
        return payoutsList.size();
    }

    static class PayoutViewHolder extends RecyclerView.ViewHolder {
        TextView tvPayoutTurfName, tvPayoutId, tvOwnerShare, tvTotalPaid, tvPayoutUpi, tvPayoutRazorpayId, tvPayoutFailureReason, badgePayoutStatus;
        Button btnRetryPayout;

        public PayoutViewHolder(@NonNull View itemView) {
            super(itemView);
            tvPayoutTurfName = itemView.findViewById(R.id.tvPayoutTurfName);
            tvPayoutId = itemView.findViewById(R.id.tvPayoutId);
            tvOwnerShare = itemView.findViewById(R.id.tvOwnerShare);
            tvTotalPaid = itemView.findViewById(R.id.tvTotalPaid);
            tvPayoutUpi = itemView.findViewById(R.id.tvPayoutUpi);
            tvPayoutRazorpayId = itemView.findViewById(R.id.tvPayoutRazorpayId);
            tvPayoutFailureReason = itemView.findViewById(R.id.tvPayoutFailureReason);
            badgePayoutStatus = itemView.findViewById(R.id.badgePayoutStatus);
            btnRetryPayout = itemView.findViewById(R.id.btnRetryPayout);
        }
    }
}
