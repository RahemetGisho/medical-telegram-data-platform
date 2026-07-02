"""
Task 3: Object Detection Module
Detects objects in downloaded Telegram images using YOLOv8.
Analyzes patterns and integrates results into data warehouse.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import csv
import json
from datetime import datetime
import numpy as np
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from ultralytics import YOLO
except ImportError:
    print("ERROR: ultralytics not installed. Run: pip install ultralytics")
    sys.exit(1)

from src.logging_config import setup_logger

logger = setup_logger("medical_warehouse.yolo_detector")


class ObjectDetector:
    """
    Production-grade YOLO object detector for image analysis.
    Detects objects, classifies images, and manages results.
    """

    # Object categories for medical/cosmetics analysis
    PRODUCT_OBJECTS = {
        "bottle",
        "container",
        "package",
        "box",
        "jar",
        "tube",
        "pill",
        "tablet",
        "capsule",
        "spray",
    }

    PERSON_OBJECTS = {
        "person",
        "people",
        "man",
        "woman",
        "human",
        "face",
        "hand",
        "body",
    }

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        image_dir: str = "data/raw/images",
        output_dir: str = "data/processed",
    ):
        """
        Initialize YOLO detector.

        Args:
            model_name: YOLO model (n=nano, s=small, m=medium)
            image_dir: Directory containing downloaded images
            output_dir: Directory to save results
        """
        self.logger = logger
        self.model_name = model_name
        self.model = None
        self._lock = threading.Lock()
        self.detection_results = []
        self.processed_images = 0
        self.failed_images = 0
        self.total_detections = 0
        self.image_dir = Path(image_dir)
        self.output_dir = Path(output_dir)

    def load_model(self) -> bool:
        """Load YOLOv8 model."""
        try:
            self.logger.info(f"Loading YOLO model: {self.model_name}")
            self.model = YOLO(self.model_name)
            self.logger.info("✓ Model loaded successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to load model: {str(e)}", exc_info=True)
            return False

    def detect_objects(
        self, image_path: str, confidence_threshold: float = 0.5
    ) -> Dict:
        """
        Run object detection on a single image.

        Args:
            image_path: Path to image file
            confidence_threshold: Minimum confidence score

        Returns:
            Dictionary with detection results
        """
        try:
            if not os.path.exists(image_path):
                self.logger.warning(f"Image not found: {image_path}")
                return {}

            # Run detection safely across multiple threads using a lock
            with self._lock:
                results = self.model(
                    image_path, conf=confidence_threshold, verbose=False
                )
            detections = []

            if results and len(results) > 0:
                boxes = results[0].boxes

                for box in boxes:
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    class_name = self.model.names[class_id]

                    detections.append(
                        {
                            "class_name": class_name,
                            "confidence": round(confidence, 3),
                            "class_id": class_id,
                        }
                    )

            self.total_detections += len(detections)
            self.processed_images += 1

            return {
                "image_path": image_path,
                "detections": detections,
                "detection_count": len(detections),
                "success": True,
            }

        except Exception as e:
            self.logger.warning(f"Error detecting objects in {image_path}: {str(e)}")
            self.failed_images += 1
            return {
                "image_path": image_path,
                "detections": [],
                "detection_count": 0,
                "success": False,
                "error": str(e),
            }

    def classify_image(self, detection_result: Dict) -> str:
        """
        Classify image based on detected objects.

        Args:
            detection_result: Dictionary from detect_objects()

        Returns:
            Image category (promotional, product_display, lifestyle, other)
        """
        if not detection_result.get("success") or not detection_result.get(
            "detections"
        ):
            return "other"

        detections = detection_result["detections"]
        detected_classes = {d["class_name"].lower() for d in detections}

        # Check for product and person detections
        has_person = bool(detected_classes & self.PERSON_OBJECTS)
        has_product = bool(detected_classes & self.PRODUCT_OBJECTS)

        # Categorize based on combinations
        if has_person and has_product:
            return "promotional"
        elif has_product and not has_person:
            return "product_display"
        elif has_person and not has_product:
            return "lifestyle"
        else:
            return "other"

    def process_all_images(self, batch_size: int = 10) -> List[Dict]:
        """
        Process all images in the data lake.

        Args:
            batch_size: Number of workers for parallel processing

        Returns:
            List of detection results
        """
        image_dir = self.image_dir

        if not image_dir.exists():
            self.logger.warning(f"Image directory not found: {image_dir}")
            return []

        # Find all images
        image_files = (
            list(image_dir.rglob("*.jpg"))
            + list(image_dir.rglob("*.png"))
            + list(image_dir.rglob("*.gif"))
            + list(image_dir.rglob("*.webp"))
        )

        self.logger.info(f"Found {len(image_files)} images to process")

        # Process in parallel
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(self._process_single_image, img_path): img_path
                for img_path in image_files
            }

            for future in as_completed(futures):
                try:
                    result = future.result()
                    self.detection_results.append(result)
                except Exception as e:
                    self.logger.error(f"Error in parallel processing: {str(e)}")

        return self.detection_results

    def _process_single_image(self, image_path: Path) -> Dict:
        """Process single image (for parallel execution)."""
        detection = self.detect_objects(str(image_path))
        classification = self.classify_image(detection)

        # Extract message_id from path: images/{channel}/{YYYY-MM-DD}/{message_id}.ext
        try:
            message_id = int(image_path.stem)
        except ValueError:
            message_id = None

        return {
            "message_id": message_id,
            "image_path": str(image_path),
            "channel_name": image_path.parent.name,
            "image_category": classification,
            "detections": detection.get("detections", []),
            "detection_count": detection.get("detection_count", 0),
            "processed_at": datetime.now().isoformat(),
        }

    def save_results_csv(self, output_path: Optional[Path] = None) -> Path:
        """
        Save detection results to CSV.

        Args:
            output_path: Path to save CSV (default: data/processed/image_detections.csv)

        Returns:
            Path to saved CSV
        """
        if output_path is None:
            output_path = self.output_dir / "image_detections.csv"

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", newline="", encoding="utf-8") as f:
                fieldnames = [
                    "message_id",
                    "image_path",
                    "channel_name",
                    "image_category",
                    "detection_count",
                    "detected_objects",
                    "processed_at",
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in self.detection_results:
                    detected_objects = "|".join(
                        [
                            f"{d['class_name']}({d['confidence']})"
                            for d in result["detections"]
                        ]
                    )

                    writer.writerow(
                        {
                            "message_id": result["message_id"],
                            "image_path": result["image_path"],
                            "channel_name": result["channel_name"],
                            "image_category": result["image_category"],
                            "detection_count": result["detection_count"],
                            "detected_objects": detected_objects,
                            "processed_at": result["processed_at"],
                        }
                    )

            self.logger.info(f"Saved detection results to {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Error saving CSV: {str(e)}", exc_info=True)
            raise

    def save_results_json(self, output_path: Optional[Path] = None) -> Path:
        """Save detailed results to JSON for warehouse loading."""
        if output_path is None:
            output_path = self.output_dir / "image_detections.json"

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "metadata": {
                            "total_images": self.processed_images,
                            "failed_images": self.failed_images,
                            "total_detections": self.total_detections,
                            "processed_at": datetime.now().isoformat(),
                            "model": self.model_name,
                        },
                        "detections": self.detection_results,
                    },
                    f,
                    indent=2,
                )

            self.logger.info(f"Saved detailed results to {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Error saving JSON: {str(e)}", exc_info=True)
            raise

    def get_summary_statistics(self) -> Dict:
        """Get summary statistics from detection results."""
        if not self.detection_results:
            return {}

        # Category distribution
        categories = {}
        for result in self.detection_results:
            cat = result["image_category"]
            categories[cat] = categories.get(cat, 0) + 1

        # Most detected objects
        all_detections = {}
        for result in self.detection_results:
            for detection in result["detections"]:
                obj_name = detection["class_name"]
                all_detections[obj_name] = all_detections.get(obj_name, 0) + 1

        top_objects = sorted(all_detections.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        # Channel distribution
        channel_dist = {}
        for result in self.detection_results:
            ch = result["channel_name"]
            channel_dist[ch] = channel_dist.get(ch, 0) + 1

        return {
            "total_images_processed": self.processed_images,
            "failed_images": self.failed_images,
            "total_detections": self.total_detections,
            "avg_detections_per_image": round(
                self.total_detections / max(self.processed_images, 1), 2
            ),
            "category_distribution": categories,
            "top_detected_objects": dict(top_objects),
            "channel_distribution": channel_dist,
        }

    def generate_report(self) -> str:
        """Generate detection report."""
        stats = self.get_summary_statistics()

        report = f"""
║         YOLO OBJECT DETECTION ANALYSIS REPORT                 ║

PROCESSING STATISTICS:
  Total Images Processed: {stats.get('total_images_processed', 0)}
  Failed Images: {stats.get('failed_images', 0)}
  Total Objects Detected: {stats.get('total_detections', 0)}
  Avg Detections/Image: {stats.get('avg_detections_per_image', 0)}

CATEGORY DISTRIBUTION:
"""

        for category, count in stats.get("category_distribution", {}).items():
            pct = (count / stats.get("total_images_processed", 1)) * 100
            report += f"  {category}: {count} ({pct:.1f}%)\n"

        report += "\nTOP DETECTED OBJECTS:\n"
        for obj_name, count in stats.get("top_detected_objects", {}).items():
            report += f"  {obj_name}: {count} images\n"

        report += "\nCHANNEL DISTRIBUTION:\n"
        for channel, count in stats.get("channel_distribution", {}).items():
            report += f"  {channel}: {count} images\n"

        return report


async def run_detection(
    image_dir: str = "data/raw/images",
    output_dir: str = "data/processed",
    model_name: str = "yolov8n.pt",
):
    """
    Main detection workflow.

    Args:
        image_dir: Directory with downloaded images
        output_dir: Directory to save results
        model_name: YOLO model name
    """
    try:
        logger.info("Starting YOLO object detection")

        # Initialize detector
        detector = ObjectDetector(
            model_name=model_name, image_dir=image_dir, output_dir=output_dir
        )

        if not detector.load_model():
            return False

        # Process all images
        logger.info("Processing images...")
        results = detector.process_all_images(batch_size=4)

        if not results:
            logger.warning("No images processed")
            return False

        # Save results
        detector.save_results_csv()
        detector.save_results_json()

        # Print report
        logger.info(detector.generate_report())

        logger.info("✓ YOLO detection completed successfully")
        return True

    except Exception as e:
        logger.error(f"Detection workflow failed: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    import asyncio

    success = asyncio.run(run_detection())
    sys.exit(0 if success else 1)
