package com.strikit.admin.adapter;

import android.content.Context;
import android.content.res.ColorStateList;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;
import com.strikit.admin.R;
import com.strikit.admin.model.RefundRequest;
import java.util.ArrayList;
import java.util.List;

public class RefundRequestAdapter extends RecyclerView.Adapter<RefundRequestAdapter.RefundViewHolder> {

    public interface OnRefundActionListener {
        void onResolveRefund(RefundRequest request);
        void onRejectRefund(RefundRequest request);
    }

    private List<RefundRequest> refundsList = new ArrayList<>();
    private final OnRefundActionListener listener;
    private final Context context;

    public RefundRequestAdapter(Context context, OnRefundActionListener listener) {
        this.context = context;
        this.listener = listener;
    }

    public void setRefunds(List<RefundRequest> refunds) {
        this.refundsList = refunds != null ? refunds : new ArrayList<>();
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public RefundViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_refund_request, parent, false);
        return new RefundViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull RefundViewHolder holder, int position) {
        RefundRequest request = refundsList.get(position);

        holder.tvRefundTurfName.setText(request.getTurfName());
        holder.tvRefundOwnerName.setText(request.getOwnerName());
        holder.tvRefundOwnerMobile.setText(request.getOwnerMobile());
        holder.tvRefundReason.setText(request.getReason());

        if (request.getCreatedAt() != null && request.getCreatedAt().length() >= 10) {
            holder.tvRefundDate.setText(request.getCreatedAt().substring(0, 10));
        } else {
            holder.tvRefundDate.setText(request.getCreatedAt());
        }

        String status = request.getStatus() != null ? request.getStatus().toUpperCase() : "PENDING";
        holder.badgeRefundStatus.setText(status);

        if ("PENDING".equals(status)) {
            holder.badgeRefundStatus.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeRefundStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_pending)));
            holder.layoutRefundActions.setVisibility(View.VISIBLE);
        } else if ("RESOLVED".equals(status)) {
            holder.badgeRefundStatus.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeRefundStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_verified)));
            holder.layoutRefundActions.setVisibility(View.GONE);
        } else { // REJECTED
            holder.badgeRefundStatus.setTextColor(ContextCompat.getColor(context, R.color.bg_dark));
            holder.badgeRefundStatus.setBackgroundTintList(ColorStateList.valueOf(ContextCompat.getColor(context, R.color.status_inactive)));
            holder.layoutRefundActions.setVisibility(View.GONE);
        }

        holder.btnResolveRefund.setOnClickListener(v -> {
            if (listener != null) {
                listener.onResolveRefund(request);
            }
        });

        holder.btnRejectRefund.setOnClickListener(v -> {
            if (listener != null) {
                listener.onRejectRefund(request);
            }
        });
    }

    @Override
    public int getItemCount() {
        return refundsList.size();
    }

    static class RefundViewHolder extends RecyclerView.ViewHolder {
        TextView tvRefundTurfName, tvRefundDate, tvRefundOwnerName, tvRefundOwnerMobile, tvRefundReason, badgeRefundStatus;
        LinearLayout layoutRefundActions;
        Button btnResolveRefund, btnRejectRefund;

        public RefundViewHolder(@NonNull View itemView) {
            super(itemView);
            tvRefundTurfName = itemView.findViewById(R.id.tvRefundTurfName);
            tvRefundDate = itemView.findViewById(R.id.tvRefundDate);
            tvRefundOwnerName = itemView.findViewById(R.id.tvRefundOwnerName);
            tvRefundOwnerMobile = itemView.findViewById(R.id.tvRefundOwnerMobile);
            tvRefundReason = itemView.findViewById(R.id.tvRefundReason);
            badgeRefundStatus = itemView.findViewById(R.id.badgeRefundStatus);
            layoutRefundActions = itemView.findViewById(R.id.layoutRefundActions);
            btnResolveRefund = itemView.findViewById(R.id.btnResolveRefund);
            btnRejectRefund = itemView.findViewById(R.id.btnRejectRefund);
        }
    }
}
