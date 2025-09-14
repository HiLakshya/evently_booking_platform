"""
Notification service for sending emails and managing notifications.
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import get_settings
from ..models.booking import Booking
from ..models.event import Event
from ..models.user import User
from ..models.waitlist import Waitlist

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for handling email notifications."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()
    
    async def send_booking_confirmation(self, booking_id: UUID) -> bool:
        """
        Send booking confirmation email to user.
        
        Args:
            booking_id: ID of the confirmed booking
            
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Get booking details with related data
            booking = await self._get_booking_with_details(booking_id)
            if not booking:
                logger.error(f"Booking {booking_id} not found")
                return False
            
            # Prepare email content
            subject = f"Booking Confirmation - {booking.event.name}"
            template_data = {
                "user_name": f"{booking.user.first_name} {booking.user.last_name}",
                "event_name": booking.event.name,
                "event_date": booking.event.event_date.strftime("%B %d, %Y at %I:%M %p"),
                "venue": booking.event.venue,
                "quantity": booking.quantity,
                "total_amount": f"${booking.total_amount:.2f}",
                "booking_id": str(booking.id),
                "booking_date": booking.created_at.strftime("%B %d, %Y at %I:%M %p")
            }
            
            html_content = self._render_booking_confirmation_template(template_data)
            text_content = self._render_booking_confirmation_text(template_data)
            
            # Send email
            success = await self._send_email(
                to_email=booking.user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            if success:
                logger.info(f"Booking confirmation sent for booking {booking_id}")
            else:
                logger.error(f"Failed to send booking confirmation for booking {booking_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending booking confirmation for {booking_id}: {e}")
            return False
    
    async def send_booking_cancellation(self, booking_id: UUID) -> bool:
        """
        Send booking cancellation email to user.
        
        Args:
            booking_id: ID of the cancelled booking
            
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Get booking details with related data
            booking = await self._get_booking_with_details(booking_id)
            if not booking:
                logger.error(f"Booking {booking_id} not found")
                return False
            
            # Prepare email content
            subject = f"Booking Cancellation - {booking.event.name}"
            template_data = {
                "user_name": f"{booking.user.first_name} {booking.user.last_name}",
                "event_name": booking.event.name,
                "event_date": booking.event.event_date.strftime("%B %d, %Y at %I:%M %p"),
                "venue": booking.event.venue,
                "quantity": booking.quantity,
                "total_amount": f"${booking.total_amount:.2f}",
                "booking_id": str(booking.id),
                "cancellation_date": datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
            }
            
            html_content = self._render_booking_cancellation_template(template_data)
            text_content = self._render_booking_cancellation_text(template_data)
            
            # Send email
            success = await self._send_email(
                to_email=booking.user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            if success:
                logger.info(f"Booking cancellation sent for booking {booking_id}")
            else:
                logger.error(f"Failed to send booking cancellation for booking {booking_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending booking cancellation for {booking_id}: {e}")
            return False
    
    async def send_waitlist_availability_notification(self, waitlist_id: UUID, available_quantity: int) -> bool:
        """
        Send waitlist availability notification to user.
        
        Args:
            waitlist_id: ID of the waitlist entry
            available_quantity: Number of seats available
            
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Get waitlist details with related data
            waitlist_entry = await self._get_waitlist_with_details(waitlist_id)
            if not waitlist_entry:
                logger.error(f"Waitlist entry {waitlist_id} not found")
                return False
            
            # Prepare email content
            subject = f"Seats Available - {waitlist_entry.event.name}"
            template_data = {
                "user_name": f"{waitlist_entry.user.first_name} {waitlist_entry.user.last_name}",
                "event_name": waitlist_entry.event.name,
                "event_date": waitlist_entry.event.event_date.strftime("%B %d, %Y at %I:%M %p"),
                "venue": waitlist_entry.event.venue,
                "available_quantity": available_quantity,
                "requested_quantity": waitlist_entry.requested_quantity,
                "price": f"${waitlist_entry.event.price:.2f}",
                "booking_deadline": (datetime.utcnow().replace(hour=23, minute=59, second=59)).strftime("%B %d, %Y at %I:%M %p"),
                "event_id": str(waitlist_entry.event.id)
            }
            
            html_content = self._render_waitlist_notification_template(template_data)
            text_content = self._render_waitlist_notification_text(template_data)
            
            # Send email
            success = await self._send_email(
                to_email=waitlist_entry.user.email,
                subject=subject,
                html_content=html_content,
                text_content=text_content
            )
            
            if success:
                logger.info(f"Waitlist notification sent for waitlist {waitlist_id}")
            else:
                logger.error(f"Failed to send waitlist notification for waitlist {waitlist_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending waitlist notification for {waitlist_id}: {e}")
            return False
    
    async def send_event_cancellation_notification(self, event_id: UUID) -> int:
        """
        Send event cancellation notifications to all booked users.
        
        Args:
            event_id: ID of the cancelled event
            
        Returns:
            int: Number of notifications sent successfully
        """
        try:
            # Get event details
            event = await self._get_event_with_bookings(event_id)
            if not event:
                logger.error(f"Event {event_id} not found")
                return 0
            
            sent_count = 0
            
            # Send notification to each user with confirmed bookings
            for booking in event.bookings:
                if booking.status.value == "confirmed":
                    try:
                        # Prepare email content
                        subject = f"Event Cancelled - {event.name}"
                        template_data = {
                            "user_name": f"{booking.user.first_name} {booking.user.last_name}",
                            "event_name": event.name,
                            "event_date": event.event_date.strftime("%B %d, %Y at %I:%M %p"),
                            "venue": event.venue,
                            "quantity": booking.quantity,
                            "total_amount": f"${booking.total_amount:.2f}",
                            "booking_id": str(booking.id),
                            "cancellation_date": datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
                        }
                        
                        html_content = self._render_event_cancellation_template(template_data)
                        text_content = self._render_event_cancellation_text(template_data)
                        
                        # Send email
                        success = await self._send_email(
                            to_email=booking.user.email,
                            subject=subject,
                            html_content=html_content,
                            text_content=text_content
                        )
                        
                        if success:
                            sent_count += 1
                            logger.info(f"Event cancellation sent to {booking.user.email}")
                        else:
                            logger.error(f"Failed to send event cancellation to {booking.user.email}")
                            
                    except Exception as e:
                        logger.error(f"Error sending event cancellation to booking {booking.id}: {e}")
            
            logger.info(f"Sent {sent_count} event cancellation notifications for event {event_id}")
            return sent_count
            
        except Exception as e:
            logger.error(f"Error sending event cancellation notifications for {event_id}: {e}")
            return 0
    
    async def send_event_update_notification(self, event_id: UUID, update_message: str) -> int:
        """
        Send event update notifications to all booked users.
        
        Args:
            event_id: ID of the updated event
            update_message: Message describing the update
            
        Returns:
            int: Number of notifications sent successfully
        """
        try:
            # Get event details
            event = await self._get_event_with_bookings(event_id)
            if not event:
                logger.error(f"Event {event_id} not found")
                return 0
            
            sent_count = 0
            
            # Send notification to each user with confirmed bookings
            for booking in event.bookings:
                if booking.status.value == "confirmed":
                    try:
                        # Prepare email content
                        subject = f"Event Update - {event.name}"
                        template_data = {
                            "user_name": f"{booking.user.first_name} {booking.user.last_name}",
                            "event_name": event.name,
                            "event_date": event.event_date.strftime("%B %d, %Y at %I:%M %p"),
                            "venue": event.venue,
                            "update_message": update_message,
                            "booking_id": str(booking.id),
                            "update_date": datetime.utcnow().strftime("%B %d, %Y at %I:%M %p")
                        }
                        
                        html_content = self._render_event_update_template(template_data)
                        text_content = self._render_event_update_text(template_data)
                        
                        # Send email
                        success = await self._send_email(
                            to_email=booking.user.email,
                            subject=subject,
                            html_content=html_content,
                            text_content=text_content
                        )
                        
                        if success:
                            sent_count += 1
                            logger.info(f"Event update sent to {booking.user.email}")
                        else:
                            logger.error(f"Failed to send event update to {booking.user.email}")
                            
                    except Exception as e:
                        logger.error(f"Error sending event update to booking {booking.id}: {e}")
            
            logger.info(f"Sent {sent_count} event update notifications for event {event_id}")
            return sent_count
            
        except Exception as e:
            logger.error(f"Error sending event update notifications for {event_id}: {e}")
            return 0
    
    async def _send_email(self, to_email: str, subject: str, html_content: str, text_content: str) -> bool:
        """
        Send email using SMTP.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content
            
        Returns:
            bool: True if email was sent successfully
        """
        try:
            # Check if email configuration is available
            if not self.settings.smtp_server or not self.settings.smtp_username:
                logger.warning("Email configuration not available, skipping email send")
                return False
            
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.settings.smtp_username
            msg["To"] = to_email
            
            # Add text and HTML parts
            text_part = MIMEText(text_content, "plain")
            html_part = MIMEText(html_content, "html")
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.settings.smtp_server, self.settings.smtp_port) as server:
                if self.settings.smtp_use_tls:
                    server.starttls()
                
                server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    async def _get_booking_with_details(self, booking_id: UUID) -> Optional[Booking]:
        """Get booking with user and event details."""
        stmt = (
            select(Booking)
            .where(Booking.id == booking_id)
            .join(Booking.user)
            .join(Booking.event)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_waitlist_with_details(self, waitlist_id: UUID) -> Optional[Waitlist]:
        """Get waitlist entry with user and event details."""
        stmt = (
            select(Waitlist)
            .where(Waitlist.id == waitlist_id)
            .join(Waitlist.user)
            .join(Waitlist.event)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_event_with_bookings(self, event_id: UUID) -> Optional[Event]:
        """Get event with all confirmed bookings and user details."""
        stmt = (
            select(Event)
            .where(Event.id == event_id)
            .join(Event.bookings)
            .join(Booking.user)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()    

    # Email Template Methods
    
    def _render_booking_confirmation_template(self, data: Dict) -> str:
        """Render HTML template for booking confirmation."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Booking Confirmation</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .booking-details {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
                .button {{ background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Booking Confirmed!</h1>
                </div>
                <div class="content">
                    <p>Dear {data['user_name']},</p>
                    <p>Your booking has been confirmed! Here are your booking details:</p>
                    
                    <div class="booking-details">
                        <h3>Event Details</h3>
                        <p><strong>Event:</strong> {data['event_name']}</p>
                        <p><strong>Date & Time:</strong> {data['event_date']}</p>
                        <p><strong>Venue:</strong> {data['venue']}</p>
                        <p><strong>Quantity:</strong> {data['quantity']} ticket(s)</p>
                        <p><strong>Total Amount:</strong> {data['total_amount']}</p>
                        <p><strong>Booking ID:</strong> {data['booking_id']}</p>
                        <p><strong>Booking Date:</strong> {data['booking_date']}</p>
                    </div>
                    
                    <p>Please save this email as your booking confirmation. You may need to present this at the event.</p>
                    <p>We look forward to seeing you at the event!</p>
                </div>
                <div class="footer">
                    <p>Thank you for using Evently!</p>
                    <p>If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _render_booking_confirmation_text(self, data: Dict) -> str:
        """Render plain text template for booking confirmation."""
        return f"""
        BOOKING CONFIRMED!
        
        Dear {data['user_name']},
        
        Your booking has been confirmed! Here are your booking details:
        
        EVENT DETAILS
        Event: {data['event_name']}
        Date & Time: {data['event_date']}
        Venue: {data['venue']}
        Quantity: {data['quantity']} ticket(s)
        Total Amount: {data['total_amount']}
        Booking ID: {data['booking_id']}
        Booking Date: {data['booking_date']}
        
        Please save this email as your booking confirmation. You may need to present this at the event.
        
        We look forward to seeing you at the event!
        
        Thank you for using Evently!
        If you have any questions, please contact our support team.
        """
    
    def _render_booking_cancellation_template(self, data: Dict) -> str:
        """Render HTML template for booking cancellation."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Booking Cancellation</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f44336; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .booking-details {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Booking Cancelled</h1>
                </div>
                <div class="content">
                    <p>Dear {data['user_name']},</p>
                    <p>Your booking has been cancelled. Here are the details of the cancelled booking:</p>
                    
                    <div class="booking-details">
                        <h3>Cancelled Booking Details</h3>
                        <p><strong>Event:</strong> {data['event_name']}</p>
                        <p><strong>Date & Time:</strong> {data['event_date']}</p>
                        <p><strong>Venue:</strong> {data['venue']}</p>
                        <p><strong>Quantity:</strong> {data['quantity']} ticket(s)</p>
                        <p><strong>Total Amount:</strong> {data['total_amount']}</p>
                        <p><strong>Booking ID:</strong> {data['booking_id']}</p>
                        <p><strong>Cancellation Date:</strong> {data['cancellation_date']}</p>
                    </div>
                    
                    <p>If you cancelled this booking yourself, no further action is required.</p>
                    <p>If you believe this cancellation was made in error, please contact our support team immediately.</p>
                </div>
                <div class="footer">
                    <p>Thank you for using Evently!</p>
                    <p>If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _render_booking_cancellation_text(self, data: Dict) -> str:
        """Render plain text template for booking cancellation."""
        return f"""
        BOOKING CANCELLED
        
        Dear {data['user_name']},
        
        Your booking has been cancelled. Here are the details of the cancelled booking:
        
        CANCELLED BOOKING DETAILS
        Event: {data['event_name']}
        Date & Time: {data['event_date']}
        Venue: {data['venue']}
        Quantity: {data['quantity']} ticket(s)
        Total Amount: {data['total_amount']}
        Booking ID: {data['booking_id']}
        Cancellation Date: {data['cancellation_date']}
        
        If you cancelled this booking yourself, no further action is required.
        If you believe this cancellation was made in error, please contact our support team immediately.
        
        Thank you for using Evently!
        If you have any questions, please contact our support team.
        """
    
    def _render_waitlist_notification_template(self, data: Dict) -> str:
        """Render HTML template for waitlist availability notification."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Seats Available!</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #FF9800; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .event-details {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
                .button {{ background-color: #FF9800; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0; }}
                .urgent {{ color: #f44336; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Seats Available!</h1>
                </div>
                <div class="content">
                    <p>Dear {data['user_name']},</p>
                    <p>Great news! Seats are now available for the event you're waitlisted for:</p>
                    
                    <div class="event-details">
                        <h3>Event Details</h3>
                        <p><strong>Event:</strong> {data['event_name']}</p>
                        <p><strong>Date & Time:</strong> {data['event_date']}</p>
                        <p><strong>Venue:</strong> {data['venue']}</p>
                        <p><strong>Available Seats:</strong> {data['available_quantity']}</p>
                        <p><strong>You Requested:</strong> {data['requested_quantity']} ticket(s)</p>
                        <p><strong>Price per Ticket:</strong> {data['price']}</p>
                    </div>
                    
                    <p class="urgent">⏰ URGENT: You have until {data['booking_deadline']} to complete your booking!</p>
                    
                    <p>To secure your tickets, please log in to your account and complete your booking as soon as possible.</p>
                    <p>If you don't complete your booking by the deadline, the seats will be offered to the next person on the waitlist.</p>
                </div>
                <div class="footer">
                    <p>Thank you for using Evently!</p>
                    <p>If you have any questions, please contact our support team.</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _render_waitlist_notification_text(self, data: Dict) -> str:
        """Render plain text template for waitlist availability notification."""
        return f"""
        SEATS AVAILABLE!
        
        Dear {data['user_name']},
        
        Great news! Seats are now available for the event you're waitlisted for:
        
        EVENT DETAILS
        Event: {data['event_name']}
        Date & Time: {data['event_date']}
        Venue: {data['venue']}
        Available Seats: {data['available_quantity']}
        You Requested: {data['requested_quantity']} ticket(s)
        Price per Ticket: {data['price']}
        
        ⏰ URGENT: You have until {data['booking_deadline']} to complete your booking!
        
        To secure your tickets, please log in to your account and complete your booking as soon as possible.
        If you don't complete your booking by the deadline, the seats will be offered to the next person on the waitlist.
        
        Thank you for using Evently!
        If you have any questions, please contact our support team.
        """
    
    def _render_event_cancellation_template(self, data: Dict) -> str:
        """Render HTML template for event cancellation notification."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Event Cancelled</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f44336; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .event-details {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Event Cancelled</h1>
                </div>
                <div class="content">
                    <p>Dear {data['user_name']},</p>
                    <p>We regret to inform you that the following event has been cancelled:</p>
                    
                    <div class="event-details">
                        <h3>Cancelled Event Details</h3>
                        <p><strong>Event:</strong> {data['event_name']}</p>
                        <p><strong>Original Date & Time:</strong> {data['event_date']}</p>
                        <p><strong>Venue:</strong> {data['venue']}</p>
                        <p><strong>Your Booking:</strong> {data['quantity']} ticket(s)</p>
                        <p><strong>Amount Paid:</strong> {data['total_amount']}</p>
                        <p><strong>Booking ID:</strong> {data['booking_id']}</p>
                        <p><strong>Cancellation Date:</strong> {data['cancellation_date']}</p>
                    </div>
                    
                    <p>We sincerely apologize for any inconvenience this may cause.</p>
                    <p>A full refund will be processed automatically and should appear in your account within 5-7 business days.</p>
                    <p>If you have any questions about your refund or need assistance, please contact our support team.</p>
                </div>
                <div class="footer">
                    <p>Thank you for your understanding.</p>
                    <p>Evently Support Team</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _render_event_cancellation_text(self, data: Dict) -> str:
        """Render plain text template for event cancellation notification."""
        return f"""
        EVENT CANCELLED
        
        Dear {data['user_name']},
        
        We regret to inform you that the following event has been cancelled:
        
        CANCELLED EVENT DETAILS
        Event: {data['event_name']}
        Original Date & Time: {data['event_date']}
        Venue: {data['venue']}
        Your Booking: {data['quantity']} ticket(s)
        Amount Paid: {data['total_amount']}
        Booking ID: {data['booking_id']}
        Cancellation Date: {data['cancellation_date']}
        
        We sincerely apologize for any inconvenience this may cause.
        A full refund will be processed automatically and should appear in your account within 5-7 business days.
        If you have any questions about your refund or need assistance, please contact our support team.
        
        Thank you for your understanding.
        Evently Support Team
        """
    
    def _render_event_update_template(self, data: Dict) -> str:
        """Render HTML template for event update notification."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Event Update</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #2196F3; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .event-details {{ background-color: white; padding: 15px; margin: 15px 0; border-radius: 5px; }}
                .update-message {{ background-color: #e3f2fd; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid #2196F3; }}
                .footer {{ text-align: center; padding: 20px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Event Update</h1>
                </div>
                <div class="content">
                    <p>Dear {data['user_name']},</p>
                    <p>We have an important update regarding your upcoming event:</p>
                    
                    <div class="event-details">
                        <h3>Event Details</h3>
                        <p><strong>Event:</strong> {data['event_name']}</p>
                        <p><strong>Date & Time:</strong> {data['event_date']}</p>
                        <p><strong>Venue:</strong> {data['venue']}</p>
                        <p><strong>Your Booking ID:</strong> {data['booking_id']}</p>
                    </div>
                    
                    <div class="update-message">
                        <h3>Update Information</h3>
                        <p>{data['update_message']}</p>
                        <p><strong>Update Date:</strong> {data['update_date']}</p>
                    </div>
                    
                    <p>Please review this update carefully as it may affect your event experience.</p>
                    <p>If you have any questions or concerns, please contact our support team.</p>
                </div>
                <div class="footer">
                    <p>Thank you for using Evently!</p>
                    <p>Evently Support Team</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _render_event_update_text(self, data: Dict) -> str:
        """Render plain text template for event update notification."""
        return f"""
        EVENT UPDATE
        
        Dear {data['user_name']},
        
        We have an important update regarding your upcoming event:
        
        EVENT DETAILS
        Event: {data['event_name']}
        Date & Time: {data['event_date']}
        Venue: {data['venue']}
        Your Booking ID: {data['booking_id']}
        
        UPDATE INFORMATION
        {data['update_message']}
        Update Date: {data['update_date']}
        
        Please review this update carefully as it may affect your event experience.
        If you have any questions or concerns, please contact our support team.
        
        Thank you for using Evently!
        Evently Support Team
        """